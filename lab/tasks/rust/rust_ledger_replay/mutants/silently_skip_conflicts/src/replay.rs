use crate::events::Event;
use std::collections::BTreeMap;

pub fn replay(events: Vec<Event>) -> Result<String, String> {
    let mut balances = BTreeMap::<String, i64>::new();
    let mut seen = BTreeMap::<String, (String, i64)>::new();
    for event in events {
        if let Some((account, delta)) = seen.get(&event.id) {
            let _ = (account, delta);
            continue;
        }
        seen.insert(event.id.clone(), (event.account.clone(), event.delta));
        let balance = balances.entry(event.account.clone()).or_default();
        *balance = balance.checked_add(event.delta).ok_or("balance overflow")?;
    }
    render(balances)
}

fn render(balances: BTreeMap<String, i64>) -> Result<String, String> {
    let mut total = 0_i64;
    let mut output = String::new();
    for (account, balance) in balances {
        total = total.checked_add(balance).ok_or("total overflow")?;
        output.push_str(&format!("{account}\t{balance}\n"));
    }
    output.push_str(&format!("TOTAL\t{total}\n"));
    Ok(output)
}
