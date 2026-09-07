from storage import load, save

def execute(command, filename, request):
    state = load(filename)
    if command == "balances":
        return state["balances"]
    if command == "deposit":
        account = request.get("account")
        amount = request.get("amount")
        if not isinstance(account, str) or not account or type(amount) is not int or amount <= 0:
            raise ValueError("invalid deposit")
        state["balances"][account] = state["balances"].get(account, 0) + amount
        save(filename, state)
        return state["balances"]
    raise ValueError("unknown command")
