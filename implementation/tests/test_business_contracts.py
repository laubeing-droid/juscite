import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from receipt_projection import project
from goal_basis import basis,strategy_status

def receipts():return [
 {'event_id':'A','kind':'receipt','source_id':'a','holder':'client','amount':'30000','evidence_ref':'receipt-a'},
 {'event_id':'B','kind':'receipt','source_id':'b','holder':'client','amount':'100000','evidence_ref':'receipt-b'},
 {'event_id':'Q','kind':'receipt','source_id':'q','holder':'court','amount':'50000','evidence_ref':'receipt-q'},
 {'event_id':'R','kind':'refund','source_id':'b','amount':'10000','evidence_ref':'refund-r'}]

class ContractTests(unittest.TestCase):
 def test_cash_before_transfer(self):
  self.assertEqual(project(receipts()),{'source_total':'180000.00','client_gross':'130000.00','client_net':'120000.00','court_held':'50000.00','refund_total':'10000.00'})
 def test_same_source_transfer_not_new_receipt(self):
  e={'event_id':'T','kind':'transfer','source_id':'q','from':'court','to':'client','amount':'50000','evidence_ref':'transfer-t'}
  r=project(receipts()+[e,e]);self.assertEqual(r['source_total'],'180000.00');self.assertEqual(r['client_net'],'170000.00');self.assertEqual(r['client_gross'],'180000.00')
 def test_conflicting_retry_rejected(self):
  e=receipts()[0];b={**e,'amount':'31000'}
  with self.assertRaisesRegex(ValueError,'idempotency_conflict'):project([e,b])
 def test_duplicate_source_not_double_counted(self):
  e=receipts()[0]
  with self.assertRaisesRegex(ValueError,'duplicate_money_source'):project([e,{**e,'event_id':'A2'}])
 def test_goal_only_change_invalidates_strategy(self):
  a=basis(fact_revision='f1',law_revision='l1',goal_revision='g1');b=basis(fact_revision='f1',law_revision='l1',goal_revision='g2')
  self.assertEqual(strategy_status(a,b),'STALE_REQUIRES_REVIEW')
 def test_missing_or_invalid_basis_never_current(self):
  for value in (None,'',123,'legacy'):
   self.assertEqual(strategy_status(value,value),'STALE_REQUIRES_REVIEW')

if __name__=='__main__':unittest.main()
