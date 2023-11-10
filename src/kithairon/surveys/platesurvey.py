import os
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Self, cast

import lxml.etree as ET
import polars as pl
from loguru import logger as log
from pydantic import BeforeValidator, NonNegativeInt, PlainSerializer, model_validator
from pydantic_xml import BaseXmlModel, attr

if TYPE_CHECKING:
    from .surveydata import SurveyData

Barcode = Annotated[
    str | None,
    PlainSerializer(
        lambda val: val if val is not None else "UnknownBarCode",
        when_used="unless-none",
    ),
    BeforeValidator(lambda val: val if val != "UnknownBarCode" else None),
]

FloatNullZero = Annotated[
    float | None,
    BeforeValidator(lambda val: val if val != 0 else None),
    PlainSerializer(lambda val: val if val is not None else 0, when_used="unless-none"),
]


class SignalFeature(BaseXmlModel, tag="f"):
    feature_type: str = attr(name="t")
    tof: float = attr(name="o")
    vpp: float = attr(name="v")


class EchoSignal(BaseXmlModel, tag="e"):
    signal_type: str = attr(name="t")
    transducer_x: float = attr(name="x")
    transducer_y: float = attr(name="y")
    transducer_z: float = attr(name="z")
    features: list[SignalFeature]


class WellSurvey(BaseXmlModel, tag="w"):
    row: NonNegativeInt = attr(name="r")
    column: NonNegativeInt = attr(name="c")
    well: str = attr(name="n")
    volume: FloatNullZero = attr(name="vl")
    current_volume: FloatNullZero = attr(name="cvl")
    status: str = attr()
    fluid: str = attr(name="fld")
    fluid_units: str = attr(name="fldu")
    meniscus_x: float = attr(name="x")
    meniscus_y: float = attr(name="y")
    fluid_composition: float = attr(name="s")
    dmso_homogeneous: float = attr(name="fsh")
    dmso_inhomogeneous: float = attr(name="fsinh")
    fluid_thickness: float = attr(name="t")
    current_fluid_thickness: float = attr(name="ct")
    bottom_thickness: float = attr(name="b")
    fluid_thickness_homogeneous: float = attr(name="fth")
    fluid_thickness_imhomogeneous: float = attr(name="ftinh")
    outlier: float = attr(name="o")
    corrective_action: str = attr(name="a")
    echo_signal: EchoSignal


class EchoPlateSurveyXML(BaseXmlModel, tag="platesurvey"):
    """A platesurvey XML model for files generated by the Medman / 'Echo Liquid Handler' software."""

    plate_type: str = attr(name="name")
    """The `name` attribute.  Practically appears to always be the plate type."""
    plate_barcode: Barcode = attr(name="barcode")
    """Plate barcode, if present, or `"UnknownBarCode"`. `barcode` attribute."""
    timestamp: datetime = attr(name="date")
    """Timestamp of the survey.  `date` attribute."""
    instrument_serial_number: str = attr(name="serial_number")
    vtl: int = attr(name="vtl")  # fixme
    original: int = attr(name="original")  # fixme
    data_format_version: int = attr(name="frmt")  # fixme
    survey_rows: int = attr(name="rows", description="Number of rows in the survey")
    """Number of rows in the survey.  `rows` attribute."""
    survey_columns: int = attr(
        name="cols", description="Number of columns in the survey"
    )
    """Number of columns in the survey.  `cols` attribute."""
    survey_total_wells: int = attr(name="totalWells")
    wells: list[WellSurvey]
    plate_name: str | None = attr(name="plate_name", default=None)
    """Plate name.  Additional attribute, added by kithairon."""
    comment: str | None = attr(name="note", default=None)
    """Comment.  Additional attribute, added by kithairon."""

    @model_validator(mode="after")
    def check_number_of_wells(self) -> Self:
        """Check that the number of wells matches the number of rows and columns."""
        if len(self.wells) != self.survey_total_wells:
            raise ValueError(
                f"Number of well data items ({len(self.wells)}) does not match reported ({self.survey_total_wells})"
            )
        return self

    @model_validator(mode="after")
    def check_data_format_version(self) -> Self:
        if self.data_format_version != 1:
            log.warning(
                "Unexpected data format version {self.data_format_version}."
                " This library has been tested on version 1."
            )
        return self

    @classmethod
    def read_xml(cls, path: os.PathLike | str) -> Self:
        """Read a platesurvey XML file."""
        return cls.from_xml_tree(ET.parse(path, parser=ET.XMLParser()).getroot())

    def write_xml(
        self,
        path: os.PathLike[str] | str | Callable[[Self], str],
        path_str_format: bool = True,
        **kwargs,
    ) -> str | os.PathLike[str]:
        """Write a platesurvey XML file."""
        if hasattr(path, "format") and path_str_format:
            path = cast(str, path).format(self.model_dump(exclude=["wells"]))  # type: ignore
        elif isinstance(path, Callable):
            path = path(self)
        ET.ElementTree(self.to_xml_tree()).write(path, **kwargs)
        return path

    def to_polars(self) -> pl.DataFrame:
        md = self.model_dump()
        wells = md.pop("wells")
        return pl.from_records(wells).with_columns(
            **{k: pl.lit(v) for k, v in md.items()}
        )

    def to_surveydata(self) -> "SurveyData":
        from .surveydata import SurveyData

        return SurveyData(self.to_polars())
