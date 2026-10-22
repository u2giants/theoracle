"""Compatibility forwarding to the SAME canonical pure core module."""
import sys
from oracle_brain.operating_model import natural_question_v1 as _canonical
sys.modules[__name__]=_canonical
