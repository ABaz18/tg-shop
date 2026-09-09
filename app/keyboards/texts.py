from app.i18n import EN, RU

# Old labels still match after a keyboard refresh via /start.
CATALOG = {RU["btn.catalog"], EN["btn.catalog"], "🛍 Каталог", "🛍 Catalog"}
PROFILE = {RU["btn.profile"], EN["btn.profile"], "👤 Профиль", "👤 Profile"}
BALANCE = {RU["btn.balance"], EN["btn.balance"], "💳 Баланс", "💳 Balance"}
REF = {RU["btn.referral"], EN["btn.referral"], "👥 Рефералка", "👥 Referral"}
SUPPORT = {RU["btn.support"], EN["btn.support"], "🆘 Поддержка", "🆘 Support"}
SETTINGS = {
    RU["btn.settings"],
    EN["btn.settings"],
    "⚙️ Настройки",
    "⚙ Настройки",
    "⚙️ Settings",
    "⚙ Settings",
}
ADMIN = {RU["btn.admin"], EN["btn.admin"], "🛠 Админка", "🛠 Admin"}
MENU = CATALOG | PROFILE | BALANCE | REF | SUPPORT | SETTINGS | ADMIN
