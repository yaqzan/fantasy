#!/usr/bin/env python3
"""
Test the /api/analyze endpoint performance
"""
import time
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_analyze_endpoint():
    print("Testing /api/analyze endpoint...")
    print("=" * 50)
    
    try:
        from app import app
        
        with app.test_client() as client:
            start_time = time.time()
            response = client.get('/api/analyze')
            end_time = time.time()
            
            print(f"Response time: {end_time - start_time:.2f} seconds")
            print(f"Status code: {response.status_code}")
            print(f"Response size: {len(response.data)} bytes")
            
            if response.status_code == 200:
                print("✅ SUCCESS: Endpoint is working!")
            else:
                print(f"❌ ERROR: Status {response.status_code}")
                print(f"Response: {response.data.decode()}")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_analyze_endpoint()
