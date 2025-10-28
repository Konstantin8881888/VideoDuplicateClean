import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget, QLabel, QFileDialog,
                             QTextEdit)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDuplicate Cleaner")
        self.setGeometry(100, 100, 800, 600)

        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Создаем layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Добавляем элементы
        label = QLabel("VideoDuplicate Cleaner - поиск похожих видеофайлов")
        layout.addWidget(label)

        self.select_button = QPushButton("Выбрать папку для сканирования")
        self.select_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_button)

        self.scan_button = QPushButton("Начать сканирование")
        self.scan_button.clicked.connect(self.start_scan)
        layout.addWidget(self.scan_button)

        # Текстовое поле для вывода результатов
        self.log_text = QTextEdit()
        self.log_text.setPlaceholderText("Здесь будут отображаться результаты...")
        layout.addWidget(self.log_text)

        self.status_label = QLabel("Готов к работе")
        layout.addWidget(self.status_label)

        # Переменная для хранения выбранной папки
        self.selected_folder = ""

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            self.selected_folder = folder
            self.log_text.append(f"Выбрана папка: {folder}")
            self.status_label.setText(f"Выбрана папка: {os.path.basename(folder)}")

    def start_scan(self):
        if not self.selected_folder:
            self.log_text.append("ОШИБКА: Сначала выберите папку!")
            return

        self.log_text.append("Начинаем сканирование...")
        self.status_label.setText("Сканирование...")

        # Здесь будет логика сканирования
        self.log_text.append(f"Сканируем: {self.selected_folder}")

        # Пока просто имитируем работу
        self.log_text.append("Найдено 5 видеофайлов")
        self.log_text.append("Анализируем...")
        self.log_text.append("Готово!")
        self.status_label.setText("Сканирование завершено")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()