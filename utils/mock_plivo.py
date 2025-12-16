# class MockPlivoClient:
#     """Mock Plivo client that completely bypasses validation"""
    
#     def __init__(self, auth_id=None, auth_token=None):
#         # Completely ignore credentials
#         print("Using Mock Plivo Client - No validation")
#         pass
    
#     @property
#     def applications(self):
#         return self
    
#     def create(self, **kwargs):
#         print(f"Mock: Creating application {kwargs.get('app_name')}")
#         return type('obj', (object,), {
#             'app_id': f"MOCK_APP_{id(self)}"
#         })()
    
#     @property
#     def calls(self):
#         return self
    
#     def create(self, **kwargs):
#         print(f"Mock: Creating call to {kwargs.get('to')}")
#         return type('obj', (object,), {
#             'call_uuid': f"MOCK_CALL_{id(self)}",
#             '__iter__': lambda self: iter([self])  # For bulk calls
#         })()