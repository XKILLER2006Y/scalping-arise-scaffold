"""Trailing exits + portfolio correlation cap."""
from app.trade_planning.trail import chandelier_stop, new_trail_state, update_trail
from app.intelligence.portfolio import check as pf_check
from app.execution.engine import PaperBroker

TOL = 1e-9


def test_chandelier_math():
    assert abs(chandelier_stop("LONG", [10, 11, 12], [9, 9, 9], 1.0, 2.5) - (12 - 2.5)) < TOL
    assert abs(chandelier_stop("SHORT", [9, 9, 9], [8, 7, 6], 1.0, 2.5) - (6 + 2.5)) < TOL
    assert chandelier_stop("LONG", [], [], 1.0) is None


def test_trail_ratchets_never_loosens_and_exits():
    st = new_trail_state("LONG", 100.0, 97.0, tp1=101.5, tp_cap=106.0)
    r1 = update_trail(st, 102.0, 100.5, 1.0)  # pushes high to 102
    assert r1["exit"] is False and r1["stop"] > 97.0
    # TP1 hit -> breakeven discipline: stop floored at entry on later bars
    r2 = update_trail(st, 103.0, 102.0, 1.0)
    assert r2["stop"] >= 100.0
    r3 = update_trail(st, 101.0, 99.0, 1.0)  # low under stop -> trail exit
    assert r3["exit"] is True and r3["reason"] == "TRAIL"


def test_portfolio_cap_blocks_stacking():
    pos = [{"direction": "LONG", "symbol": "XAU/USD", "risk_money": 100.0},
           {"direction": "LONG", "symbol": "XAU/USD", "risk_money": 100.0}]
    r = pf_check(pos, "LONG", "XAU/USD", 100.0, 10000.0)
    assert r["allowed"] is False and "correlation cap" in r["reason"]
    r2 = pf_check(pos, "SHORT", "XAU/USD", 100.0, 10000.0)
    assert r2["allowed"] is True
    r3 = pf_check([], "LONG", "XAU/USD", 400.0, 10000.0)
    assert r3["allowed"] is False and "book risk" in r3["reason"]


def test_broker_enforces_portfolio_cap():
    b = PaperBroker()
    plan = {"feasible": True, "action": "BUY", "direction": "LONG", "entry": 2650.0,
            "stop": 2647.0, "take_profit": 2656.0, "lots": 0.01, "risk_money": 100.0}
    assert b.execute_trade(dict(plan))["status"] == "filled"
    assert b.execute_trade(dict(plan))["status"] == "filled"
    third = b.execute_trade(dict(plan))
    assert third["status"] == "rejected" and "correlation" in third["reason"]


def test_backtest_trail_mode_runs():
    from app.market_data.providers.base import synth_candles
    from app.market_data.models import SourceType
    from app.backtesting.engine import run_backtest
    import datetime
    day = datetime.datetime.now(datetime.timezone.utc).replace(hour=6, minute=30, second=0, microsecond=0)
    cs = synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=700, start=int(day.timestamp()))
    r = run_backtest(cs, exit_mode="trail")
    assert set(r) >= {"trades", "net_pnl", "gate"}
