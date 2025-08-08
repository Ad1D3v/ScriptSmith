from e2b_code_interpreter import Sandbox

# Handle Sandbox
def initialize_sandbox(session_state) -> None:
    try:
        if session_state.sandbox:
            try:
                session_state.sandbox.close()
            except:
                pass
        
        # Initialize sandbox with 60 second timeout
        session_state.sandbox = Sandbox(timeout=60)
    except Exception as e:
        session_state.sandbox = None