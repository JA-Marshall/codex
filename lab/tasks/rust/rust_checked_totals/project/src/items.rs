pub struct Item {
    pub label: String,
    pub quantity: u64,
    pub price: u64,
}

pub fn parse(input: &str) -> Result<Vec<Item>, String> {
    let mut items = Vec::new();
    for (index, line) in input.lines().enumerate() {
        if line.is_empty() {
            continue;
        }
        let fields: Vec<_> = line.split('\t').collect();
        let fail = || format!("line {}: invalid item", index + 1);
        if fields.len() != 3 || fields[0].is_empty() {
            return Err(fail());
        }
        items.push(Item {
            label: fields[0].into(),
            quantity: fields[1].parse().map_err(|_| fail())?,
            price: fields[2].parse().map_err(|_| fail())?,
        });
    }
    Ok(items)
}
