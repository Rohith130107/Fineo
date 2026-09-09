import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from src.models import TradeSignal, SignalOutput

logger = logging.getLogger(__name__)

@dataclass
class DecisionResult:
    action: TradeSignal # BUY, SELL, or NEUTRAL
    confidence: float # Overall confidence (0.0 to 1.0)
    reasons: List[str]
    blackout_active: bool
    module_signals: Dict[str, SignalOutput]

class ConfluenceEngine:
    """
    Confluence Decision Engine combining Price Action, Order Flow, and News Gate signals.
    Rules per PRD.md:
    1. News filter acts as a defensive gate — blocks entries if blackout_active is True.
    2. Minimum required signals (default 2 of 3, where news gate passing counts as 1 gate clearance,
       or both Price Action and Order Flow agree on direction).
    3. Confluence requires Price Action and Order Flow directions to not conflict.
    """
    def __init__(self, min_signals_required: int = 2, min_confidence: float = 0.5):
        self.min_signals_required = min_signals_required
        self.min_confidence = min_confidence

    def evaluate(self, pa_signal: SignalOutput, of_signal: SignalOutput, blackout_active: bool) -> DecisionResult:
        reasons = []
        module_signals = {
            "price_action": pa_signal,
            "order_flow": of_signal
        }

        # News Filter Gate Check
        if blackout_active:
            reasons.append("BLOCKED: News blackout window is active")
            return DecisionResult(
                action=TradeSignal.NEUTRAL,
                confidence=0.0,
                reasons=reasons,
                blackout_active=True,
                module_signals=module_signals
            )

        reasons.append("PASS: News gate open")

        # Evaluate directional agreement between Price Action and Order Flow
        pa_dir = pa_signal.signal
        of_dir = of_signal.signal

        # If they directly conflict (BUY vs SELL), no trade
        if pa_dir != TradeSignal.NEUTRAL and of_dir != TradeSignal.NEUTRAL and pa_dir != of_dir:
            reasons.append(f"CONFLICT: Price Action ({pa_dir.value}) vs Order Flow ({of_dir.value})")
            return DecisionResult(
                action=TradeSignal.NEUTRAL,
                confidence=0.0,
                reasons=reasons,
                blackout_active=False,
                module_signals=module_signals
            )

        # Determine target direction
        target_dir = TradeSignal.NEUTRAL
        if pa_dir != TradeSignal.NEUTRAL:
            target_dir = pa_dir
        elif of_dir != TradeSignal.NEUTRAL:
            target_dir = of_dir

        if target_dir == TradeSignal.NEUTRAL:
            reasons.append("NEUTRAL: Neither Price Action nor Order Flow generated directional signal")
            return DecisionResult(
                action=TradeSignal.NEUTRAL,
                confidence=0.0,
                reasons=reasons,
                blackout_active=False,
                module_signals=module_signals
            )

        # Count confirming signals:
        # News gate pass = +1
        # Price Action matching = +1
        # Order Flow matching = +1
        signal_count = 1 # Start with 1 for passing news gate

        confidences = []
        if pa_dir == target_dir and pa_signal.confidence >= self.min_confidence:
            signal_count += 1
            confidences.append(pa_signal.confidence)
            reasons.append(f"CONFIRM: Price Action agrees ({pa_dir.value}, conf={pa_signal.confidence:.2f})")

        if of_dir == target_dir and of_signal.confidence >= self.min_confidence:
            signal_count += 1
            confidences.append(of_signal.confidence)
            reasons.append(f"CONFIRM: Order Flow agrees ({of_dir.value}, conf={of_signal.confidence:.2f})")

        if signal_count >= self.min_signals_required and confidences:
            avg_confidence = float(sum(confidences) / len(confidences))
            reasons.append(f"DECISION: {target_dir.value} confirmed with {signal_count} signals")
            return DecisionResult(
                action=target_dir,
                confidence=avg_confidence,
                reasons=reasons,
                blackout_active=False,
                module_signals=module_signals
            )
        else:
            reasons.append(f"INSUFFICIENT: Got {signal_count} signals, required {self.min_signals_required}")
            return DecisionResult(
                action=TradeSignal.NEUTRAL,
                confidence=0.0,
                reasons=reasons,
                blackout_active=False,
                module_signals=module_signals
            )
