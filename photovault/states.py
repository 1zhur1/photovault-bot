"""FSM-состояния для многошаговых сценариев."""

from aiogram.fsm.state import State, StatesGroup


class NewFolder(StatesGroup):
    name = State()


class RenameFolder(StatesGroup):
    name = State()


class EditNote(StatesGroup):
    text = State()


class Search(StatesGroup):
    query = State()


class Upload(StatesGroup):
    active = State()