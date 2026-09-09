from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    topup_custom = State()
    promo = State()
    support = State()


class AdminStates(StatesGroup):
    cat_ru = State()
    cat_en = State()
    prd_cat = State()
    prd_ru = State()
    prd_en = State()
    prd_desc_ru = State()
    prd_desc_en = State()
    prd_price = State()
    prd_part = State()
    stock_paste = State()
    user_query = State()
    user_balance = State()
    role_query = State()
    channel_id = State()
    channel_url = State()
    channel_title = State()
    ref_values = State()
    broadcast = State()
    promo_code = State()
    promo_amount = State()
    texts = State()
    ticket_reply = State()
    prd_cover = State()
    shop_banner = State()
    cat_cover = State()
    find_product = State()
    channel_fwd = State()
