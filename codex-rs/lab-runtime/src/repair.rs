pub(crate) fn prompt(base: &str, attempt: u8, failures: &str) -> String {
    format!("{base}\nRepair round {attempt}: host-observed verifier commands failed checks: {failures}. Diagnose by rerunning these approved checks; fix the implementation within the same plan, then report all completed steps. Do not weaken assertions to obtain success. Request an amendment for material strategy changes.")
}
