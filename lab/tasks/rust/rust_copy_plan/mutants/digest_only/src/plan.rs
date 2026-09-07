use crate::manifest::Manifest;
use std::collections::BTreeSet;

pub fn diff(source: &Manifest, target: &Manifest, keep_extra: bool) -> Result<String, String> {
    let paths: BTreeSet<_> = source.keys().chain(target.keys()).collect();
    let mut output = String::new();
    let (mut copies, mut deletes, mut bytes) = (0_u64, 0_u64, 0_u64);
    for path in paths {
        match (source.get(path), target.get(path)) {
            (Some(entry), old) => {
                if old.is_none_or(|previous| previous.digest != entry.digest) {
                    copies += 1;
                    bytes = bytes.checked_add(entry.size).ok_or("byte total overflow")?;
                    output.push_str(&format!("COPY\t{path}\t{}\n", entry.size));
                }
            }
            (None, Some(_)) if !keep_extra => {
                deletes += 1;
                output.push_str(&format!("DELETE\t{path}\n"));
            }
            (None, Some(_)) | (None, None) => {}
        }
    }
    output.push_str(&format!("TOTAL\t{copies}\t{deletes}\t{bytes}\n"));
    Ok(output)
}
