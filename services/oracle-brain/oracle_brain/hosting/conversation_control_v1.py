"""Compatibility forwarding to the single core conversation owner."""
from oracle_brain.operating_model import conversation_control_v1 as _owner

# Forward exact classes/functions, including retained private test/API seams.
globals().update({name:value for name,value in vars(_owner).items() if not name.startswith("__")})
