"""Proposed Harness-owned receipt projection, never deployed by this package.
This records physical cash custody, NOT JC discharge/interest/legal liability.
Every source is recorded once; court->client transfers don't create new money.
Owner must bind it to command_tx, ACL, CAS and durable events before production.
"""
from decimal import Decimal, InvalidOperation

def amount(value):
    if not isinstance(value, str): raise ValueError("amount_requires_decimal_text")
    try: result=Decimal(value)
    except InvalidOperation: raise ValueError("amount_invalid") from None
    if not result.is_finite() or result <= 0:raise ValueError("amount_must_be_positive_finite")
    if result != result.quantize(Decimal("0.01")):raise ValueError("amount_requires_cent_precision")
    return result

def project(events):
    sources={};seen={};gross=Decimal(0);refunds=Decimal(0)
    for e in events:
        event_id=e['event_id']
        if event_id in seen:
            if seen[event_id]!=e:raise ValueError("idempotency_conflict")
            continue
        seen[event_id]=dict(e)
        if not e.get('evidence_ref'):raise ValueError("receipt_requires_real_evidence_ref")
        kind=e['kind'];sid=e['source_id'];n=amount(e['amount'])
        if kind=='receipt':
            if sid in sources:raise ValueError("duplicate_money_source")
            holder=e['holder']
            if holder not in ('court','client'):raise ValueError("unknown_holder")
            sources[sid]={'origin':n,'court':n if holder=='court' else Decimal(0),'client':n if holder=='client' else Decimal(0),'refund':Decimal(0)}
            if holder=='client':gross+=n
        elif kind=='transfer':
            s=sources[sid]
            if e.get('from')!='court' or e.get('to')!='client' or s['court']<n:raise ValueError("invalid_court_to_client_transfer")
            s['court']-=n;s['client']+=n;gross+=n
        elif kind=='refund':
            s=sources[sid]
            if s['client']<n:raise ValueError("refund_exceeds_source_client_balance")
            s['client']-=n;s['refund']+=n;refunds+=n
        else:raise ValueError("unknown_cash_event")
    total=sum((s['origin'] for s in sources.values()),Decimal(0))
    held=sum((s['court'] for s in sources.values()),Decimal(0))
    net=sum((s['client'] for s in sources.values()),Decimal(0))
    if total!=held+net+refunds:raise ValueError("cash_conservation_failed")
    return {k:format(v,'.2f') for k,v in {'source_total':total,'client_gross':gross,'client_net':net,'court_held':held,'refund_total':refunds}.items()}
