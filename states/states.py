from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    waiting_for_facult = State()
    waiting_for_group = State()
    waiting_for_subgroup = State()

class MainMenu(StatesGroup):
    main_menu = State()

class Settings(StatesGroup):
    settings = State()
    waiting_for_login = State()
    waiting_for_password = State()
    waiting_for_group = State()
    waiting_for_subgroup = State()
    waiting_for_facult = State()

class ScheduleSelection(StatesGroup):
    selecting_day = State()