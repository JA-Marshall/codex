def validate_transfer(operation):
    if not isinstance(operation, dict) or set(operation) != {"from", "to", "amount"}:
        raise ValueError("invalid transfer")
    source, target, amount = operation["from"], operation["to"], operation["amount"]
    if (not isinstance(source, str) or not source or not isinstance(target, str) or not target
            or source == target or type(amount) is not int or amount <= 0):
        raise ValueError("invalid transfer")
    return source, target, amount


def apply(balances, operations):
    result = dict(balances)
    if not isinstance(operations, list) or not operations:
        raise ValueError("invalid batch")
    for operation in operations:
        source, target, amount = validate_transfer(operation)
        if result.get(source, 0) < amount:
            raise ValueError("insufficient funds")
        result[source] -= amount
        result[target] = result.get(target, 0) + amount
    return result
