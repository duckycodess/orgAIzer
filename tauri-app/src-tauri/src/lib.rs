use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct ApiServer(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let (_rx, child) = app.shell().sidecar("api-server")?.spawn()?;
            app.manage(ApiServer(Mutex::new(Some(child))));

            // In release builds: hide the window until the API is reachable,
            // so the UI doesn't flash a broken state on cold start.
            #[cfg(not(debug_assertions))]
            {
                let window = app.get_webview_window("main").unwrap();
                window.hide()?;
                std::thread::spawn(move || {
                    for _ in 0..60 {
                        std::thread::sleep(std::time::Duration::from_millis(500));
                        if std::net::TcpStream::connect("127.0.0.1:8000").is_ok() {
                            break;
                        }
                    }
                    let _ = window.show();
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<ApiServer>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
