#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Write;
use std::process::{Command, Stdio};

#[tauri::command]
fn self_test_enabled() -> bool {
    std::env::args().any(|arg| arg == "--self-test-pdf")
}

#[tauri::command]
fn self_test_complete(app: tauri::AppHandle, result: serde_json::Value) -> Result<(), String> {
    if !self_test_enabled() { return Err("Test není povolen".into()); }
    let path = std::env::temp_dir().join("dataship-v2-pdf-selftest.json");
    std::fs::write(path, result.to_string()).map_err(|e| e.to_string())?;
    app.exit(0);
    Ok(())
}

#[tauri::command]
async fn report(mut request: serde_json::Value) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let engine = std::env::current_exe().map_err(|e| e.to_string())?
            .parent().ok_or("Chybí adresář aplikace")?.join("dataship-v2-engine.exe");
        let output_dir = std::env::temp_dir().join("DataShip-2-ukazkova-pdf");
        request["output_dir"] = output_dir.to_string_lossy().to_string().into();
        let mut cmd = Command::new(engine);
        #[cfg(windows)] { use std::os::windows::process::CommandExt; cmd.creation_flags(0x08000000); }
        let mut child = cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
            .spawn().map_err(|e| format!("Nelze spustit výpočet: {e}"))?;
        child.stdin.take().ok_or("Chybí vstup výpočtu")?.write_all(request.to_string().as_bytes()).map_err(|e| e.to_string())?;
        let output = child.wait_with_output().map_err(|e| e.to_string())?;
        let value: serde_json::Value = serde_json::from_slice(&output.stdout).map_err(|_| "Výpočet nevrátil platný výsledek")?;
        if value["ok"] != true { return Err(value["error"].as_str().unwrap_or("Výpočet selhal").to_string()); }
        Ok(value["data"].clone())
    }).await.map_err(|e| e.to_string())?
}

fn main() {
    std::panic::set_hook(Box::new(|info| {
        let path = std::env::temp_dir().join("dataship-v2-prototype-error.txt");
        let _ = std::fs::write(path, info.to_string());
    }));
    tauri::Builder::default().invoke_handler(tauri::generate_handler![report, self_test_enabled, self_test_complete])
        .run(tauri::generate_context!()).expect("Chyba spuštění DataShip 2");
}
