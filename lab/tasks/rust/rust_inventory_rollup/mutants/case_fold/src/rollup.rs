use std::collections::BTreeMap;

pub fn aggregate(rows: Vec<(String, i64)>) -> Result<String, String> {
    let mut totals = BTreeMap::<String, i64>::new();
    for (name, quantity) in rows {
        let total = totals.entry(name.to_lowercase()).or_default();
        *total = total.checked_add(quantity).ok_or("quantity overflow")?;
    }
    Ok(totals
        .into_iter()
        .map(|(name, quantity)| format!("{name}\t{quantity}\n"))
        .collect())
}
