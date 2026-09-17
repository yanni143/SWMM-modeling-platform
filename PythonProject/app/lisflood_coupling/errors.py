"""Errors raised only by the LISFLOOD conversion boundary."""


class LisfloodCouplingError(ValueError):
    """The SWMM artifacts cannot be converted into a LISFLOOD input."""
