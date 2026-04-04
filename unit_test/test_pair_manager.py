import sys
sys.path.insert(0, 'd:/Honda/ai_project/ai')

from core.state_manager import StateManager
from core.pair_manager import PairManager
from config import ICS_URL, VALIDATE_PAIRS

def test_data_flow():
    print("=== Testing PairManager Data Flow ===\n")
    
    # Setup
    state_manager = StateManager()
    
    # Giả lập data trong ready lists
    state_manager.ready_start_list = {"start_10000989", "start_10001773"}
    state_manager.ready_end_list = {"end_10000757", "end_10000758"}
    
    validate_pairs = {
        ("start_10000989", "end_10000757"),
        ("start_10001773", "end_10000758"),
    }
    
    # Khởi tạo PairManager với signature mới
    pair_manager = PairManager(ICS_URL, state_manager, validate_pairs)
    
    print(f"Ready start list: {state_manager.ready_start_list}")
    print(f"Ready end list: {state_manager.ready_end_list}")
    print(f"Validate pairs: {validate_pairs}\n")
    
    # Test make_pairs
    try:
        pairs, payloads = pair_manager.make_pairs()
        print(f"✓ Found {len(pairs)} ready pairs")
        print(f"✓ Generated {len(payloads)} payloads")
        
        for i, (pair, payload) in enumerate(zip(pairs, payloads), 1):
            print(f"\nPair {i}: {pair}")
            print(f"  OrderId: {payload.get('orderId')}")
            print(f"  TaskPath: {payload.get('taskOrderDetail', [{}])[0].get('taskPath')}")
        
        print("\n✓ Test PASSED - make_pairs() working correctly!")
        
    except Exception as e:
        print(f"\n✗ Test FAILED - Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_data_flow()