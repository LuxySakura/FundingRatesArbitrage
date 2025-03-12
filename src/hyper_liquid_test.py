from hyperliquid.info import Info
from hyperliquid.utils import constants

OKX_MAKER_FEE = 0.02  # OKX手续费

info = Info(constants.TESTNET_API_URL, skip_ws=True)
user_state = info.user_state("0x52aec9e53ecdee92de1690d4241850c1adb444db")
print(user_state)