from storage import load, save
from transfers import apply, validate_transfer

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
    if command == "batch":
        if (not isinstance(request, dict) or set(request) != {"id", "transfers"}
                or not isinstance(request["id"], str) or not request["id"]
                or not isinstance(request["transfers"], list) or not request["transfers"]):
            raise ValueError("invalid batch")
        receipt = state["receipts"].get(request["id"])
        if receipt is not None:
            for transfer in request["transfers"]:
                validate_transfer(transfer)
            if receipt["transfers"] != request["transfers"]:
                raise ValueError("id conflict")
            return receipt["balances"]
        for transfer in request["transfers"]:
            state["balances"] = apply(state["balances"], [transfer])
            save(filename, state)
        balances = state["balances"]
        state["balances"] = balances
        state["receipts"][request["id"]] = {"transfers": request["transfers"], "balances": balances.copy()}
        save(filename, state)
        return balances
    raise ValueError("unknown command")
