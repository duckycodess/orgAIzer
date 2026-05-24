use tauri::Manager;

#[cfg(not(debug_assertions))]
use std::sync::Mutex;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::process::CommandChild;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;

#[cfg(not(debug_assertions))]
struct ApiServer(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // In release: spawn the bundled API sidecar and wait for it before
            // showing the window. In dev, start_dev.py already runs the API.
            #[cfg(not(debug_assertions))]
            {
                let (_rx, child) = app.shell().sidecar("api-server")?.spawn()?;
                app.manage(ApiServer(Mutex::new(Some(child))));

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
                #[cfg(not(debug_assertions))]
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
