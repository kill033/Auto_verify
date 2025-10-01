import sys
import serial
import serial.tools.list_ports
from PyQt5 import QtWidgets, QtGui, QtCore
from sbus_reference import sbus_reference  # словарь в отдельном файле


class RobotGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot GUI — H12 Remote")
        self.setGeometry(50, 50, 1200, 700)
        self.setMaximumSize(1366, 768)

        self.setStyleSheet("""
            QPushButton { font-size: 9px; padding: 2px; }
            QLabel { font-size: 9px; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit { font-size: 9px; }
        """)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- Статус ---
        status_layout = QtWidgets.QHBoxLayout()
        self.port_status = QtWidgets.QLabel(" Порт: закрыт ")
        self.port_status.setAlignment(QtCore.Qt.AlignCenter)
        self.port_status.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 2px;")
        status_layout.addWidget(self.port_status)

        self.tx_status = QtWidgets.QLabel(" TX ")
        self.tx_status.setAlignment(QtCore.Qt.AlignCenter)
        self.tx_status.setStyleSheet("background-color: gray; color: white; font-weight: bold; padding: 2px;")
        status_layout.addWidget(self.tx_status)
        layout.addLayout(status_layout)

        # --- Порты ---
        port_layout = QtWidgets.QHBoxLayout()
        self.combobox = QtWidgets.QComboBox()
        self.refresh_ports()
        port_layout.addWidget(self.combobox)

        btn_open = QtWidgets.QPushButton("Открыть")
        btn_open.clicked.connect(self.open_port)
        port_layout.addWidget(btn_open)

        btn_close = QtWidgets.QPushButton("Закрыть")
        btn_close.clicked.connect(self.close_port)
        port_layout.addWidget(btn_close)

        btn_refresh = QtWidgets.QPushButton("Обновить")
        btn_refresh.clicked.connect(self.refresh_ports)
        port_layout.addWidget(btn_refresh)
        layout.addLayout(port_layout)

        # --- Настройки ---
        self.baudrate = QtWidgets.QSpinBox()
        self.baudrate.setRange(1200, 921600)
        self.baudrate.setValue(115200)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.addWidget(QtWidgets.QLabel("Baudrate:"))
        settings_layout.addWidget(self.baudrate)
        layout.addLayout(settings_layout)

        self.serial_port = None

        # --- Терминал ---
        self.terminal = QtWidgets.QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMaximumHeight(150)
        self.terminal.setStyleSheet("background-color: black; color: lime; font-family: monospace;")
        layout.addWidget(self.terminal)

        # --- Работа с логом ---
        log_layout = QtWidgets.QHBoxLayout()
        btn_load_log = QtWidgets.QPushButton("Загрузить лог")
        btn_load_log.clicked.connect(self.load_log)
        log_layout.addWidget(btn_load_log)

        btn_run_block = QtWidgets.QPushButton("Прогнать блок")
        btn_run_block.clicked.connect(self.run_selected_block)
        log_layout.addWidget(btn_run_block)

        btn_stop = QtWidgets.QPushButton("Стоп")
        btn_stop.clicked.connect(self.stop_run)
        log_layout.addWidget(btn_stop)

        btn_reset_colors = QtWidgets.QPushButton("Сбросить цвета")
        btn_reset_colors.clicked.connect(self.reset_colors)
        log_layout.addWidget(btn_reset_colors)
        layout.addLayout(log_layout)

        self.log_list = QtWidgets.QListWidget()
        self.log_list.itemDoubleClicked.connect(self.send_selected_item)
        layout.addWidget(self.log_list)

        self.progress_label = QtWidgets.QLabel("Прогнано: 0 / 0")
        layout.addWidget(self.progress_label)

        self.log_commands = []
        self.total_cmds = 0
        self.sent_cmds = 0

        # Таймеры
        self.tx_timer = QtCore.QTimer()
        self.tx_timer.setSingleShot(True)
        self.tx_timer.timeout.connect(self.reset_tx_indicator)

        self.run_timer = QtCore.QTimer()
        self.run_timer.timeout.connect(self._run_next)
        self.run_queue = []
        self.run_index = 0

    # ==== Методы ====
    def log(self, text):
        self.terminal.append(text)
        print(text)

    def refresh_ports(self):
        self.combobox.clear()
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.combobox.addItems(ports if ports else ["Нет портов"])

    def open_port(self):
        port = self.combobox.currentText()
        if port and "Нет" not in port:
            try:
                self.serial_port = serial.Serial(port, self.baudrate.value())
                self.log(f"[+] Открыл {port} @{self.baudrate.value()} baud")
                self.port_status.setText(" Порт: открыт ")
                self.port_status.setStyleSheet("background-color: green; color: white; font-weight: bold; padding: 2px;")
            except Exception as e:
                self.log(f"[!] Ошибка открытия {port}: {e}")
                self.serial_port = None

    def close_port(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.log("[×] Порт закрыт")
        self.serial_port = None
        self.port_status.setText(" Порт: закрыт ")
        self.port_status.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 2px;")

    def _write_serial(self, cmd_hex, label):
        try:
            cmd_bytes = bytes(int(x, 16) for x in cmd_hex.split())
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.write(cmd_bytes)
                self.log(f"[→] {label}: {cmd_hex}")
                self.set_tx_indicator()
            else:
                self.log(f"[!] Порт не открыт. {label}: {cmd_hex}")
        except Exception as e:
            self.log(f"[!] Ошибка кодирования {label}: {e}")

    def set_tx_indicator(self):
        self.tx_status.setStyleSheet("background-color: orange; color: black; font-weight: bold; padding: 2px;")
        self.tx_timer.start(300)

    def reset_tx_indicator(self):
        self.tx_status.setStyleSheet("background-color: gray; color: white; font-weight: bold; padding: 2px;")

    # ==== Работа с логом ====
    def load_log(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выбери calibration_log", "", "Text Files (*.txt)")
        if path:
            self.log_list.clear()
            self.log_commands.clear()
            self.total_cmds = 0
            self.sent_cmds = 0
            self.progress_label.setText("Прогнано: 0 / 0")

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # HEX команда
                    if "SBUS:" in line.upper():
                        parts = line.split("SBUS:")
                        prefix = parts[0].strip()
                        hex_str = parts[1].strip().upper()
                        item_text = f"{prefix} | {hex_str}"
                        item = QtWidgets.QListWidgetItem(item_text)
                        item.setData(QtCore.Qt.UserRole, hex_str)
                        self.log_list.addItem(item)
                        self.log_commands.append(hex_str)
                        self.total_cmds += 1
                    else:
                        # Заголовок блока
                        item = QtWidgets.QListWidgetItem(f"--- {line} ---")
                        item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                        item.setBackground(QtGui.QColor("#444"))
                        item.setForeground(QtGui.QBrush(QtGui.QColor("white")))
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        self.log_list.addItem(item)

            self.progress_label.setText(f"Прогнано: 0 / {self.total_cmds}")
            self.log(f"[+] Загружено {self.total_cmds} команд")

    def run_selected_block(self):
        item = self.log_list.currentItem()
        if not item or item.data(QtCore.Qt.UserRole):  # выбрана не шапка
            self.log("[!] Выбери заголовок блока")
            return

        # собрать команды до следующего заголовка
        start_row = self.log_list.row(item)
        self.run_queue = []
        for i in range(start_row + 1, self.log_list.count()):
            it = self.log_list.item(i)
            if not it.data(QtCore.Qt.UserRole):  # новый заголовок
                break
            if any(key in it.text() for key in ["(A)", "(B)", "(C)", "(D)"]):
                continue
            self.run_queue.append(it)

        if not self.run_queue:
            self.log("[!] В блоке нет команд для прогонки")
            return

        self.log(f"[→] Запуск блока: {item.text()} ({len(self.run_queue)} команд)")
        self.run_index = 0
        self.run_timer.start(500)

    def _run_next(self):
        if self.run_index >= len(self.run_queue):
            self.log("[✓] Блок завершён")
            self.run_timer.stop()
            return

        item = self.run_queue[self.run_index]
        cmd = item.data(QtCore.Qt.UserRole)
        if cmd:
            self.send_from_list(item, cmd)
        self.run_index += 1

    def stop_run(self):
        self.run_timer.stop()
        self.log("[×] Прогонка остановлена пользователем")

    def send_from_list(self, item, cmd):
        self._write_serial(cmd, "Log HEX (auto)")
        item.setBackground(QtGui.QColor("green"))
        self.sent_cmds += 1
        self.progress_label.setText(f"Прогнано: {self.sent_cmds} / {self.total_cmds}")

    def send_selected_item(self, item):
        cmd = item.data(QtCore.Qt.UserRole)
        if cmd:
            self._write_serial(cmd, "Log HEX (dblclick)")
            item.setBackground(QtGui.QColor("green"))
            self.sent_cmds += 1
            self.progress_label.setText(f"Прогнано: {self.sent_cmds} / {self.total_cmds}")

    def reset_colors(self):
        for i in range(self.log_list.count()):
            item = self.log_list.item(i)
            cmd = item.data(QtCore.Qt.UserRole)
            if cmd:  # только команды
                item.setBackground(QtGui.QBrush())
        self.sent_cmds = 0
        self.progress_label.setText(f"Прогнано: 0 / {self.total_cmds}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    gui = RobotGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
