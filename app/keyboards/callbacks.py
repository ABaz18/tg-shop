from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CatCB(CallbackData, prefix="c"):
    id: int
    p: int = 0


class PrdCB(CallbackData, prefix="p"):
    id: int


class BuyCB(CallbackData, prefix="b"):
    id: int


class FavCB(CallbackData, prefix="f"):
    id: int


class TopupCB(CallbackData, prefix="t"):
    k: int
    pid: int = 0


class NavCB(CallbackData, prefix="n"):
    to: str
    p: int = 0


class LangCB(CallbackData, prefix="l"):
    code: str


class SubCB(CallbackData, prefix="s"):
    act: str


class AdmCB(CallbackData, prefix="a"):
    act: str
    id: int = 0
    p: int = 0
