const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let backendProcess;

function createWindow() {
    const port = 8000;
    console.log(`Using port: ${port}`);

    let backendDir, backendScript;
    if (app.isPackaged) {
        backendDir = path.join(process.resourcesPath, 'app.asar.unpacked', 'backend');
        backendScript = path.join(backendDir, 'main.py');
    } else {
        backendDir = path.join(__dirname, 'backend');
        backendScript = path.join(backendDir, 'main.py');
    }

    console.log(`Looking for backend at: ${backendScript}`);
    if (!fs.existsSync(backendScript)) {
        dialog.showErrorBox('Ошибка', `Не найден бэкенд: ${backendScript}`);
        app.quit();
        return;
    }

    // Используем полный путь к Python (можно заменить на 'python', если он в PATH)
    const pythonExe = 'python'; // или 'C:\\Python314\\python.exe'
    backendProcess = spawn(pythonExe, [backendScript], {
        cwd: backendDir,
        env: { ...process.env, PORT: port.toString() },
        stdio: 'pipe',
        shell: true   // важно для Windows
    });

    backendProcess.stdout.on('data', (data) => {
        console.log(`[Backend stdout]: ${data}`);
    });
    backendProcess.stderr.on('data', (data) => {
        console.error(`[Backend stderr]: ${data}`);
    });
    backendProcess.on('error', (err) => {
        console.error(`[Backend error event]: ${err.message}`);
        dialog.showErrorBox('Ошибка запуска бэкенда', err.message);
    });

    // Ждём 5 секунд и открываем окно
    setTimeout(() => {
        const mainWindow = new BrowserWindow({
            width: 1200,
            height: 800,
            webPreferences: {
                nodeIntegration: false,
                contextIsolation: true,
                preload: path.join(__dirname, 'preload.js')
            }
        });

        let frontendPath;
        if (app.isPackaged) {
            frontendPath = path.join(process.resourcesPath, 'app.asar.unpacked', 'frontend', 'standalone.html');
        } else {
            frontendPath = path.join(__dirname, 'frontend', 'standalone.html');
        }
        console.log(`Loading frontend from: ${frontendPath}`);
        if (!fs.existsSync(frontendPath)) {
            dialog.showErrorBox('Ошибка', `Не найден фронтенд: ${frontendPath}`);
            app.quit();
            return;
        }
        mainWindow.loadFile(frontendPath).catch(err => {
            console.error(err);
            dialog.showErrorBox('Ошибка', 'Не удалось загрузить интерфейс.');
        });
        mainWindow.on('closed', () => {});
    }, 5000);
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (backendProcess) backendProcess.kill();
    if (process.platform !== 'darwin') app.quit();
});