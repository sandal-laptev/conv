"""conv — кроссплатформенный медиа-конвертер."""

from conv.core import (
    Converter,
    ConvertRequest,
    ConvertResult,
    OUTPUT_FORMATS,
    ALL_INPUT,
    IMAGE_INPUT,
    SVG_INPUT,
    VIDEO_INPUT,
    AUDIO_INPUT,
    detect_mime,
    resolve_format,
)

__version__ = "2.0.0"
__author__ = "Иохим Кузьмич"
__license__ = "GPLv3"
