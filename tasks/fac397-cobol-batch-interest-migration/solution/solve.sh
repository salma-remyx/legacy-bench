#!/bin/bash

cat /app/src/INTRST01.cbl
cat /app/src/COPYBOOKS/ACCOUNT-REC.cpy
cat /app/src/COPYBOOKS/CHECKPOINT-REC.cpy
cat /app/src/schema.sql
cat /app/data/CONTROL.DAT

mkdir -p /app/src

cp /app/oracle_build/Cargo.toml /app/Cargo.toml
mkdir -p /app/.cargo
cp /app/oracle_build/.cargo/config.toml /app/.cargo/config.toml

cat > /app/src/main.rs << 'RUSTEOF'
use rusqlite::{Connection, params};
use std::fs::{File, OpenOptions};
use std::io::{Read, Write, BufWriter};
use chrono::Local;

const COMMIT_INTERVAL: i64 = 100;
const DAYS_IN_YEAR: i64 = 365;
const REVIEW_THRESHOLD: f64 = 100000.0;
const MAX_WAVE: i32 = 3;

fn int_to_comp3(value: i64, digits: usize) -> Vec<u8> {
    let num_bytes = (digits + 2) / 2;
    let s = format!("{:0>width$}", value.abs(), width = digits);
    let sign: u8 = if value >= 0 { 0x0C } else { 0x0D };
    
    let total_nibbles = num_bytes * 2;
    let padding = total_nibbles - digits - 1;
    
    let mut result = vec![0u8; num_bytes];
    let chars: Vec<char> = s.chars().collect();
    let mut nibble_idx = 0;
    
    for byte_idx in 0..num_bytes {
        let high = if nibble_idx < padding {
            0
        } else if nibble_idx - padding < digits {
            chars[nibble_idx - padding].to_digit(10).unwrap() as u8
        } else {
            0
        };
        
        nibble_idx += 1;
        
        let low = if nibble_idx < padding {
            0
        } else if nibble_idx - padding < digits {
            chars[nibble_idx - padding].to_digit(10).unwrap() as u8
        } else if nibble_idx == total_nibbles - 1 {
            sign
        } else {
            0
        };
        
        result[byte_idx] = (high << 4) | low;
        nibble_idx += 1;
    }
    
    result
}

fn comp3_to_int(data: &[u8]) -> i64 {
    let mut result: i64 = 0;
    for (i, &byte) in data.iter().enumerate() {
        let high = ((byte >> 4) & 0x0F) as i64;
        let low = (byte & 0x0F) as i64;
        if i == data.len() - 1 {
            result = result * 10 + high;
            if low == 0x0D {
                result = -result;
            }
        } else {
            result = result * 10 + high;
            result = result * 10 + low;
        }
    }
    result
}

struct Checkpoint {
    last_account_id: i64,
    rows_processed: i64,
    total_interest: i64,
    job_start_time: i64,
    last_commit_time: i64,
    status: char,
}

fn read_checkpoint(path: &str) -> Checkpoint {
    let mut file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return Checkpoint {
            last_account_id: 0,
            rows_processed: 0,
            total_interest: 0,
            job_start_time: 0,
            last_commit_time: 0,
            status: 'I',
        },
    };
    
    let mut data = Vec::new();
    if file.read_to_end(&mut data).is_err() || data.len() < 37 {
        return Checkpoint {
            last_account_id: 0,
            rows_processed: 0,
            total_interest: 0,
            job_start_time: 0,
            last_commit_time: 0,
            status: 'I',
        };
    }
    
    Checkpoint {
        last_account_id: comp3_to_int(&data[0..6]),
        rows_processed: comp3_to_int(&data[6..12]),
        total_interest: comp3_to_int(&data[12..20]),
        job_start_time: comp3_to_int(&data[20..28]),
        last_commit_time: comp3_to_int(&data[28..36]),
        status: data[36] as char,
    }
}

fn write_checkpoint(path: &str, cp: &Checkpoint) {
    let mut data = Vec::new();
    data.extend(int_to_comp3(cp.last_account_id, 10));
    data.extend(int_to_comp3(cp.rows_processed, 10));
    data.extend(int_to_comp3(cp.total_interest * 100, 15));
    data.extend(int_to_comp3(cp.job_start_time, 14));
    data.extend(int_to_comp3(cp.last_commit_time, 14));
    data.push(cp.status as u8);
    
    assert!(data.len() == 37, "Checkpoint must be exactly 37 bytes, got {}", data.len());
    
    let mut file = File::create(path).expect("Cannot create checkpoint file");
    file.write_all(&data).expect("Cannot write checkpoint");
}

fn parse_control_file(path: &str) -> Option<(String, String, f64)> {
    let content = std::fs::read_to_string(path).ok()?;
    let line = content.lines().next()?;
    
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() >= 3 {
        let field = parts[0].to_lowercase();
        let op = parts[1].to_string();
        let value: f64 = parts[2].parse().ok()?;
        
        let allowed_fields = ["balance", "account_type", "status"];
        if allowed_fields.contains(&field.as_str()) && 
           [">", "<", ">=", "<=", "="].contains(&op.as_str()) {
            return Some((field, op, value));
        }
    }
    None
}

struct RateSchedule {
    base_rate: f64,
    tier1_threshold: f64,
    tier1_bonus: f64,
    tier2_threshold: f64,
    tier2_bonus: f64,
    type_c_modifier: f64,
    type_s_modifier: f64,
    type_m_modifier: f64,
}

fn calculate_interest(
    balance: f64, 
    account_rate: f64,
    account_type: &str,
    legacy_rate_flag: &str,
    schedule: &Option<RateSchedule>
) -> i64 {
    let effective_rate = if legacy_rate_flag == "Y" {
        account_rate
    } else if let Some(sched) = schedule {
        let type_modifier = match account_type {
            "C" => sched.type_c_modifier,
            "S" => sched.type_s_modifier,
            "M" => sched.type_m_modifier,
            _ => 0.0,
        };
        
        let tier_bonus = if balance > sched.tier2_threshold {
            sched.tier2_bonus
        } else if balance > sched.tier1_threshold {
            sched.tier1_bonus
        } else {
            0.0
        };
        
        sched.base_rate + type_modifier + tier_bonus
    } else {
        account_rate
    };
    
    let daily_rate = effective_rate / DAYS_IN_YEAR as f64;
    
    (balance * daily_rate).floor() as i64
}

fn get_timestamp() -> i64 {
    let now = Local::now();
    now.format("%Y%m%d%H%M%S").to_string().parse().unwrap_or(0)
}

fn main() {
    let conn = Connection::open("/app/data/batch.db").expect("Failed to connect to database");
    
    let mut checkpoint = read_checkpoint("/app/data/CHECKPOINT.DAT");
    
    let new_job = checkpoint.status == 'I' || checkpoint.status == 'C';
    let job_start = if new_job {
        get_timestamp()
    } else {
        checkpoint.job_start_time
    };
    
    let filter = parse_control_file("/app/data/CONTROL.DAT");
    
    let results_file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open("/app/results.dat")
        .expect("Cannot open results.dat");
    let mut results_writer = BufWriter::new(results_file);
    
    let audit_file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open("/app/audit.log")
        .expect("Cannot open audit.log");
    let mut audit_writer = BufWriter::new(audit_file);
    
    let mut last_account_id = if new_job { 0 } else { checkpoint.last_account_id };
    let mut rows_processed = if new_job { 0 } else { checkpoint.rows_processed };
    let mut total_interest = if new_job { 0 } else { checkpoint.total_interest };
    let mut commit_counter = 0i64;
    
    for wave in 1..=MAX_WAVE {
        let wave_last_id = if wave == 1 && !new_job { last_account_id } else { 0 };
        let mut current_last_id = wave_last_id;
        
        loop {
            let query = match &filter {
                Some((field, op, value)) => {
                    format!(
                        "SELECT a.account_id, a.account_name, a.account_type, a.status, 
                                a.balance, a.interest_rate, a.last_update,
                                a.open_date, a.parent_account_id, a.rate_schedule_id,
                                a.processing_wave, a.legacy_rate_flag,
                                r.base_rate, r.tier1_threshold, r.tier1_bonus,
                                r.tier2_threshold, r.tier2_bonus,
                                r.type_c_modifier, r.type_s_modifier, r.type_m_modifier
                         FROM accounts a
                         LEFT JOIN rate_schedules r ON a.rate_schedule_id = r.schedule_id
                         WHERE a.account_id > ?1 AND a.status = 'A' 
                           AND a.processing_wave = ?2 AND a.{} {} ?3
                         ORDER BY a.account_id
                         LIMIT 100",
                        field, op
                    )
                },
                None => {
                    "SELECT a.account_id, a.account_name, a.account_type, a.status, 
                            a.balance, a.interest_rate, a.last_update,
                            a.open_date, a.parent_account_id, a.rate_schedule_id,
                            a.processing_wave, a.legacy_rate_flag,
                            r.base_rate, r.tier1_threshold, r.tier1_bonus,
                            r.tier2_threshold, r.tier2_bonus,
                            r.type_c_modifier, r.type_s_modifier, r.type_m_modifier
                     FROM accounts a
                     LEFT JOIN rate_schedules r ON a.rate_schedule_id = r.schedule_id
                     WHERE a.account_id > ?1 AND a.status = 'A' AND a.processing_wave = ?2
                     ORDER BY a.account_id
                     LIMIT 100".to_string()
                }
            };
            
            let rows: Vec<(i64, String, String, String, f64, f64, i64, i64, Option<i64>, 
                          String, i32, String, Option<f64>, Option<f64>, Option<f64>,
                          Option<f64>, Option<f64>, Option<f64>, Option<f64>, Option<f64>)> = {
                let mut stmt = conn.prepare(&query).expect("Failed to prepare query");
                
                let result = match &filter {
                    Some((_, _, value)) => {
                        stmt.query_map(params![current_last_id, wave, value], |row| {
                            Ok((
                                row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                                row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?,
                                row.get(8)?, row.get(9)?, row.get(10)?, row.get(11)?,
                                row.get(12)?, row.get(13)?, row.get(14)?, row.get(15)?,
                                row.get(16)?, row.get(17)?, row.get(18)?, row.get(19)?,
                            ))
                        }).expect("Query failed").filter_map(|r| r.ok()).collect()
                    },
                    None => {
                        stmt.query_map(params![current_last_id, wave], |row| {
                            Ok((
                                row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                                row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?,
                                row.get(8)?, row.get(9)?, row.get(10)?, row.get(11)?,
                                row.get(12)?, row.get(13)?, row.get(14)?, row.get(15)?,
                                row.get(16)?, row.get(17)?, row.get(18)?, row.get(19)?,
                            ))
                        }).expect("Query failed").filter_map(|r| r.ok()).collect()
                    }
                };
                result
            };
            
            if rows.is_empty() {
                break;
            }
            
            for row in rows {
                let (account_id, _name, acc_type, _status, balance, account_rate, 
                     old_last_update, _open_date, _parent_id, _schedule_id,
                     _proc_wave, legacy_flag, base_rate, tier1_thresh, tier1_bonus,
                     tier2_thresh, tier2_bonus, type_c_mod, type_s_mod, type_m_mod) = row;
                
                current_last_id = account_id;
                
                if old_last_update >= job_start && checkpoint.status == 'R' {
                    continue;
                }
                
                let schedule = if let (Some(br), Some(t1t), Some(t1b), Some(t2t), Some(t2b),
                                      Some(tcm), Some(tsm), Some(tmm)) = 
                    (base_rate, tier1_thresh, tier1_bonus, tier2_thresh, tier2_bonus,
                     type_c_mod, type_s_mod, type_m_mod) {
                    Some(RateSchedule {
                        base_rate: br,
                        tier1_threshold: t1t,
                        tier1_bonus: t1b,
                        tier2_threshold: t2t,
                        tier2_bonus: t2b,
                        type_c_modifier: tcm,
                        type_s_modifier: tsm,
                        type_m_modifier: tmm,
                    })
                } else {
                    None
                };
                
                let interest = calculate_interest(balance, account_rate, &acc_type, &legacy_flag, &schedule);
                let new_balance = balance + interest as f64;
                let current_time = get_timestamp();
                
                conn.execute(
                    "UPDATE accounts SET balance = ?1, last_update = ?2 WHERE account_id = ?3",
                    params![new_balance, current_time, account_id]
                ).expect("Update failed");
                
                writeln!(audit_writer, "{:010}|{}|{}|{}|{}", 
                    account_id, balance, interest, new_balance, current_time)
                    .expect("Cannot write audit");
                
                if balance <= REVIEW_THRESHOLD {
                    writeln!(results_writer, "{:010}|{}", account_id, interest)
                        .expect("Cannot write results");
                }
                
                last_account_id = account_id;
                rows_processed += 1;
                total_interest += interest;
                commit_counter += 1;
                
                if commit_counter >= COMMIT_INTERVAL {
                    checkpoint = Checkpoint {
                        last_account_id,
                        rows_processed,
                        total_interest,
                        job_start_time: job_start,
                        last_commit_time: get_timestamp(),
                        status: 'R',
                    };
                    write_checkpoint("/app/data/CHECKPOINT.DAT", &checkpoint);
                    commit_counter = 0;
                }
            }
        }
        println!("Wave {} complete", wave);
    }
    
    results_writer.flush().expect("Cannot flush results");
    audit_writer.flush().expect("Cannot flush audit");
    
    checkpoint = Checkpoint {
        last_account_id,
        rows_processed,
        total_interest,
        job_start_time: job_start,
        last_commit_time: get_timestamp(),
        status: 'C',
    };
    write_checkpoint("/app/data/CHECKPOINT.DAT", &checkpoint);
    
    println!("Batch complete. Rows processed: {}, Total interest: {}", rows_processed, total_interest);
}
RUSTEOF

cd /app
cargo build --release 2>&1

cp /app/target/release/batch_processor /app/batch_processor 2>/dev/null || true

/app/target/release/batch_processor

echo "=== Results (first 20 lines) ==="
head -20 /app/results.dat
echo "=== Audit Log (first 20 lines) ==="
head -20 /app/audit.log
echo "=== Checkpoint ==="
python3 -c "data=open('/app/data/CHECKPOINT.DAT','rb').read(); print(' '.join(f'{b:02x}' for b in data))"
