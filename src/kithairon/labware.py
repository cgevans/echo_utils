import os
import typing
from typing import Optional, cast

import polars as pl
from pydantic_xml import BaseXmlModel, attr


class PlateInfo(BaseXmlModel, tag="plateinfo"):
    platetype: str = attr()
    plateformat: str = attr()
    usage: str = attr()
    fluid: Optional[str] = attr(default=None)
    manufacturer: str = attr()
    lotnumber: str = attr()
    partnumber: str = attr()
    rows: int = attr()
    cols: int = attr(name="cols")  # FIXME
    a1offsety: int = attr()
    centerspacingx: int = attr()
    centerspacingy: int = attr()
    plateheight: int = attr()
    skirtheight: int = attr()
    wellwidth: int = attr()
    welllength: int = attr()
    wellcapacity: int = attr()
    bottominset: float = attr()
    centerwellposx: float = attr()
    centerwellposy: float = attr()
    minwellvol: Optional[float] = attr(default=None)
    maxwellvol: Optional[float] = attr(default=None)
    maxvoltotal: Optional[float] = attr(default=None)
    minvolume: Optional[float] = attr(default=None)
    dropvolume: Optional[float] = attr(default=None)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.rows, self.cols)


PLATE_INFO_SCHEMA = {
    k: cast(
        type,
        v.annotation
        if not (type_union := typing.get_args(v.annotation))
        else type_union[0],
    )
    for k, v in PlateInfo.model_fields.items()
}


class PlateInfoELWDest(PlateInfo):
    @property
    def usage(self) -> str:
        return "DEST"

    @property
    def welllength(self) -> int:
        return self.wellwidth

    @property
    def plateformat(self) -> str:
        return "UNKNOWN"


class PlateInfoELWSrc(PlateInfo):
    @property
    def usage(self) -> str:
        return "SRC"

    @property
    def welllength(self) -> int:
        return self.wellwidth

    @property
    def plateformat(self) -> str:
        return "UNKNOWN"


class SourcePlateListELWX(BaseXmlModel, tag="sourceplates"):
    plates: list[PlateInfo]


class DestinationPlateListELWX(BaseXmlModel, tag="destinationplates"):
    plates: list[PlateInfo]


class SourcePlateListELW(BaseXmlModel, tag="sourceplates"):
    plates: list[PlateInfoELWSrc]


class DestinationPlateListELW(BaseXmlModel, tag="destinationplates"):
    plates: list[PlateInfoELWDest]


class EchoLabwareELWX(BaseXmlModel, tag="EchoLabware"):
    sourceplates: SourcePlateListELWX
    destinationplates: DestinationPlateListELWX


class EchoLabwareELW(BaseXmlModel, tag="EchoLabware"):
    sourceplates: SourcePlateListELW
    destinationplates: DestinationPlateListELW


class Labware:
    _plates: list[PlateInfo]

    def __init__(self, plates: list[PlateInfo]):
        self._plates = plates

    @classmethod
    def from_raw(cls, raw: EchoLabwareELWX | EchoLabwareELW):
        return cls(
            cast(list[PlateInfo], raw.sourceplates.plates)
            + cast(list[PlateInfo], raw.destinationplates.plates)
        )

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "Labware":
        xmlstr = open(path).read()
        try:
            return cls.from_raw(EchoLabwareELWX.from_xml(xmlstr))
        except Exception:
            return cls.from_raw(EchoLabwareELW.from_xml(xmlstr))

    def to_file(self, path: str | os.PathLike[str], **kwargs):
        """Write an ELWX labware file.

        Parameters
        ----------
        path : str | os.PathLike[str]
            path to write to
        """
        xmlstr = self.to_xml(**kwargs)
        match xmlstr:
            case str():
                open(path, "w").write(xmlstr)
            case bytes():
                open(path, "wb").write(xmlstr)

    def to_xml(self, **kwargs) -> str | bytes:
        """Generate an ELWX XML string.

        Parameters
        ----------
        **kwargs
            passed to pydantic_xml.BaseXmlModel.to_xml

        Returns
        -------
        str | bytes
            XML string
        """
        return self.to_elwx().to_xml(**kwargs)

    def to_polars(self) -> pl.DataFrame:
        return pl.from_records(self._plates, schema=PLATE_INFO_SCHEMA)

    def to_elwx(self) -> EchoLabwareELWX:
        return EchoLabwareELWX(
            sourceplates=SourcePlateListELWX(
                plates=[plate for plate in self._plates if plate.usage == "SRC"]
            ),
            destinationplates=DestinationPlateListELWX(
                plates=[plate for plate in self._plates if plate.usage == "DEST"]
            ),
        )

    def __getitem__(self, platetype: str):
        for plate in self._plates:
            if plate.platetype == platetype:
                return plate
        raise KeyError(platetype)

    def keys(self):
        return [plate.platetype for plate in self._plates]

    def add(self, plate: PlateInfo):
        if plate.platetype in self.keys():
            raise KeyError(f"Plate of type {plate.platetype} already exists.")
        self._plates.append(plate)