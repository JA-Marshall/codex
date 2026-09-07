use crate::items::Item;
use std::collections::BTreeMap;

pub fn summarize(items: Vec<Item>) -> Result<String, String> {
    let mut groups = BTreeMap::<String, u64>::new();
    for item in items {
        let amount = item
            .quantity
            .checked_mul(item.price)
            .ok_or("overflow: row amount")?;
        let group = groups.entry(item.label).or_default();
        *group = group.checked_add(amount).ok_or("overflow: label total")?;
    }
    let mut grand = 0_u64;
    let mut output = String::new();
    for (label, amount) in groups {
        grand = grand.wrapping_add(amount);
        output.push_str(&format!("{label}\t{amount}\n"));
    }
    output.push_str(&format!("GRAND\t{grand}\n"));
    Ok(output)
}
