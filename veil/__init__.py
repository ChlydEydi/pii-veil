"""pii-veil: keep real personal data away from cloud AI.

    from veil import Shield
    shield = Shield()
    safe = shield.mask("Email John Smith at john.smith@acme.com")
    answer = some_cloud_ai(safe)
    print(shield.unmask(answer))
"""
from .detect import LocalLLMDetector, RuleDetector
from .shield import Shield

__all__ = ["Shield", "RuleDetector", "LocalLLMDetector"]
__version__ = "0.1.0"
