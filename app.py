from os import path
import sys
import configparser
import sqlite3
from PyQt5.QtCore import Qt, QTimer, QFile, QTextStream
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QPushButton,
    QLineEdit,
    QSizePolicy,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
)
#import BreezeStyleSheets
import pkg_resources
from main_view_ui import Ui_MainWindow
from flowlayout import FlowLayout
from datetime import datetime, timedelta

config = {
    "TABLES": {
        "projects_table": "CREATE TABLE projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(128) NOT NULL UNIQUE, started_at datetime NOT NULL, ended_at datetime);",
        "tasks_table": "CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name VARCHAR(128) NOT NULL UNIQUE, started_at datetime NOT NULL, ended_at datetime, count INTEGER, unique(project_id, name));",
        "timestamps_table": "CREATE TABLE timestamps(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, started_at datetime NOT NULL, ended_at datetime NOT NULL, count INTEGER);"
        },
    "SCHEMES": {
        "projects_scheme": "id, name, started_at, ended_at",
        "tasks_scheme": "id, project_id, name, started_at, ended_at, count",
        "timestamps_scheme": "id, task_id, started_at, ended_at, count"
        },
    "base_state":{
        "auto_save": 300000
        }
    }

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        style_sheet = pkg_resources.resource_filename(__name__,'BreezeStyleSheets/dark.qss')
        file = QFile(style_sheet)
        file.open(QFile.ReadOnly | QFile.Text)
        stream = QTextStream(file)
        self.setStyleSheet(stream.readAll())
        self.project_format = "Flex_Grid"
        self.project_dict = {}
        self.database_file = None

        self.config_file = pkg_resources.resource_filename(__name__,'time-tracker.config')
        self.config = configparser.ConfigParser()
        with open(self.config_file, 'r') as conf:
            self.config.read_file(conf)
        
        if self.config.has_section("state") and 'file' in self.config['state']:
        #if "state" in self.config and 'file' in self.config['state']:
            if not path.exists(self.config["state"]["file"]):
                self.open_file_dialog(True)

            self.database_file = self.config["state"].get("file")
            self.populate_from_db()

            if "auto_save" in self.config["state"]:
                save_interval = int(self.config["state"].get("auto_save"))
            else:
                save_interval = int(self.config["base_state"].get("auto_save"))
            self.auto_save = QTimer()
            self.auto_save.timeout.connect(self.write_state)
            self.auto_save.start(int(save_interval))

        self.connectSignalsSlots()

    def open_file_dialog(self, new_file=False):
        if new_file:
            file, check = QFileDialog.getSaveFileName(
                None,
                "Neue Datenbank anlegen",
                "",
                "Datenbank (*.db);;Alle Dateitypen (*)",
            )
            if check:
                self.database_file = file
                db = sqlite3.connect(self.database_file)
                try:
                    for table in self.config["TABLES"]:
                        table_statement = self.config["TABLES"][table]
                        db.execute(table_statement)
                        print(table_statement)
                        self.statusBar().showMessage("Datenbank wurde angelegt.")
                except Exception:
                    self.statusBar().showMessage("Datenbank nicht leer, lade Inhalte.")
                db.commit()
                db.close()
        else:
            file, check = QFileDialog.getOpenFileName(
                None,
                "Bestehende Datenbank öffnen",
                "",
                "Datenbank (*.db);;Alle Dateitypen (*)",
            )
            if check:
                self.database_file = file

        if check:
            self.populate_from_db()
            self.config["state"]["file"] = self.database_file
            with open(self.config_file, "w") as conf:
                self.config.write(conf)
            return file
        else:
            self.statusBar().showMessage("Es wurde keine Datenbank angelegt.")

    def clean_canvas(self):
        for project in self.project_dict:
            for task in self.project_dict[project]["tasks"]:
                self.delete_task(self.project_dict[project]["tasks"][task]["task_obj"],permanent=False)
            self.project_dict[project]["tab"].setParent(None)
            self.project_dict[project]["tab"].deleteLater()
        self.project_dict = {}
    
    def populate_from_db(self):
        self.clean_canvas()
        if self.database_file:
            print("Attempting to load State from {}".format(self.database_file))
            projects_scheme = self.config["SCHEMES"].get("projects_scheme").split(", ")
            tasks_scheme = self.config["SCHEMES"].get("tasks_scheme").split(", ")
            with sqlite3.connect(self.database_file) as db:
                conn = db.cursor()
                try:
                    print("Loading Projects...")
                    conn.execute(
                        "SELECT {keys} FROM projects;".format(
                            keys=", ".join(projects_scheme)
                        )
                    )
                    projects_tuple = conn.fetchall()
                    for project in projects_tuple:
                        self.project_dict[project[1]] = {
                            "id": project[0],
                            "name": project[1],
                            "started_at": project[2],
                            "ended_at": project[3],
                            "tasks": {},
                            "tab": None,
                        }
                    print("Projects loaded.")
                except Exception as e:
                    print(e)
                try:
                    print("Loading tasks...")
                    for project in self.project_dict:
                        conn.execute(
                            "SELECT {keys} FROM tasks WHERE project_id = {pid};".format(
                                keys=", ".join(tasks_scheme),
                                pid=self.project_dict[project]["id"],
                            )
                        )
                        tasks_tuple = conn.fetchall()
                        print(tasks_tuple)
                        for task in tasks_tuple:
                            self.project_dict[project]["tasks"][task[2]] = {
                                "id": task[0],
                                "project_id": task[1],
                                "name": task[2],
                                "started_at": task[3],
                                "ended_at": task[4],
                                "time_slots": [],
                                "task_obj": None,
                                "count": task[5],
                            }
                            print("Loaded Task {}".format(task[2]))
                            sql = "SELECT SUM(count) FROM timestamps WHERE task_id = {};".format(
                                task[0]
                            )
                            conn.execute(sql)
                            cnt = conn.fetchone()[0]
                            if cnt:
                                self.project_dict[project]["tasks"][task[2]][
                                    "count"
                                ] = int(cnt)
                            else:
                                self.project_dict[project]["tasks"][task[2]][
                                    "count"
                                ] = 0
                    print("All tasks loaded.")

                except Exception as e:
                    print(e)
            print("Project-Dict: {}".format(self.project_dict))
            self.draw_state()

    def draw_state(self):
        for project in self.project_dict:
            print("Drawing {}".format(project))
            self.new_project(project)

            for task in self.project_dict[project]["tasks"]:
                print("Drawing {}".format(task))
                self.new_task(project, task)

    def write_state(self):
        projects_scheme = self.config["SCHEMES"].get("projects_scheme").split(", ")
        tasks_scheme = self.config["SCHEMES"].get("tasks_scheme").split(", ")
        to_db = {"projects": [], "tasks": [], "timestamps": []}

        for project in self.project_dict:
            temp_proj = {}
            for key in projects_scheme:
                if key in self.project_dict[project]:
                    temp_proj[key] = self.project_dict[project][key]
                else:
                    temp_proj[key] = ""
            to_db["projects"].append(temp_proj)

            for task in self.project_dict[project]["tasks"]:
                for timestamp in self.project_dict[project]["tasks"][task][
                    "time_slots"
                ]:
                    to_db["timestamps"].append(timestamp)

                temp_task = {}
                for key in tasks_scheme:
                    if key in self.project_dict[project]["tasks"][task]:
                        temp_task[key] = self.project_dict[project]["tasks"][task][key]
                    else:
                        temp_task[key] = ""
                to_db["tasks"].append(temp_task)

        if not self.database_file:
            return
        with sqlite3.connect(self.database_file) as db:
            cursor = db.cursor()
            for item in to_db["projects"]:
                sql_insert = "REPLACE INTO {} ({}) VALUES('{}');".format(
                    "projects",
                    ", ".join([key for key in item]),
                    "', '".join([str(item[key]) for key in item]),
                )
                cursor.execute(sql_insert)
            for item in to_db["tasks"]:
                sql_insert = "REPLACE INTO {} ({}) VALUES('{}');".format(
                    "tasks",
                    ", ".join([key for key in item]),
                    "', '".join([str(item[key]) for key in item]),
                )
                cursor.execute(sql_insert)
            for item in to_db["timestamps"]:
                sql_insert = "INSERT INTO {} ({}) VALUES('{}');".format(
                    "timestamps",
                    ", ".join([key for key in item]),
                    "', '".join([str(item[key]) for key in item]),
                )
                cursor.execute(sql_insert)

    def connectSignalsSlots(self):
        self.action_about.triggered.connect(self.about)
        self.action_new_projekt.triggered.connect(self.new_project)
        self.action_open_file.triggered.connect(lambda: self.open_file_dialog(False))
        self.action_new.triggered.connect(lambda: self.open_file_dialog(True))

    def closeEvent(self, event):
        print("Saving state...")
        self.write_state()
        print("Finished!")
        self.close

    def register_db_id(self, type: str, object_dict):
        if type == "project":
            type = "projects"
            scheme = self.config["SCHEMES"].get("projects_scheme").split(", ")
        elif type == "task":
            type = "tasks"
            scheme = self.config["SCHEMES"].get("tasks_scheme").split(", ")
        with sqlite3.connect(self.database_file) as db:
            cursor = db.cursor()
            sql_insert = "INSERT INTO {} ({}) VALUES('{}');".format(
                type,
                ", ".join(
                    [
                        item
                        for item in scheme
                        if item in object_dict and object_dict[item]
                    ]
                ),
                "', '".join(
                    [
                        str(object_dict[item])
                        for item in object_dict
                        if item in scheme and object_dict[item]
                    ]
                ),
            )
            print(sql_insert)
            cursor.execute(sql_insert)
            cursor.execute(
                "SELECT id FROM {} WHERE name = '{}';".format(type, object_dict["name"])
            )
            id = cursor.fetchone()[0]

            return id

    def showTime(self, task):
        # checking if flag is true
        if task.flag:
            task.count += 1
        text = str(timedelta(seconds=task.count))
        task.zLabel.setText(text)

    def start_stopwatch(self, task, project_name):
        task.flag = True
        task.active_timer["started_at"] = datetime.now()

    def stop_stopwatch(self, task, project_name):
        task.flag = False
        timer = task.active_timer
        timer["ended_at"] = datetime.now()
        delta = timer["ended_at"] - timer["started_at"]
        timer["count"] = delta.total_seconds()

        task_dict = self.project_dict[project_name]["tasks"][task.task_name]
        task_dict["time_slots"].append(task.active_timer.copy())
        task.active_timer = {
            "started_at": None,
            "ended_at": None,
            "task_id": task_dict["id"],
            "count": 0,
        }

    def delete_task(self, task, permanent=True):
        if task.flag:
            self.stop_stopwatch(task, task.project_name)
        if permanent:
            dlg = DeleteDialog(task.task_name)
            if dlg.exec():
                print(task.parent().vLayout.gLayout.removeWidget(task))
                task_id = self.project_dict[task.project_name]["tasks"][task.task_name][
                    "id"
                ]
                self.project_dict[task.project_name]["tasks"].pop(task.task_name)
                with sqlite3.connect(self.database_file) as db:
                    cursor = db.cursor()
                    cursor.execute("DELETE FROM tasks WHERE id = {}".format(task_id))
                print(task_id)

        task.deleteLater()

    def summarize_time(self, tab):
        project = self.project_dict[tab.project_name]
        total_count = 0
        for task in project["tasks"]:
            if (
                "task_obj" in project["tasks"][task]
                and project["tasks"][task]["task_obj"]
            ):
                total_count += project["tasks"][task]["task_obj"].count
        text = str(timedelta(seconds=total_count))
        tab.zLabel.setText(text)

    def new_project(self, project_name=None):
        if not project_name:
            project_name, ok = QInputDialog.getText(
                self,
                "Name des Projekts",
                "Projektname",
                QLineEdit.Normal,
                "Neues Projekt",
            )
            if not ok:
                return
            if project_name in self.project_dict:
                self.statusBar().showMessage(
                    "Es existiert bereits ein Projekt unter diesem Namen!"
                )
                return
            project_dict = {
                "id": None,
                "name": project_name,
                "started_at": datetime.now(),
                "ended_at": None,
                "tab": None,
                "tasks": {},
            }
            project_dict["id"] = self.register_db_id("project", project_dict.copy())
            self.project_dict[project_name] = project_dict
        else:
            ok = True

        if ok:
            tab = QWidget()

            tab_timer = QTimer(tab)

            tab.project_name = project_name
            self.ProjektVerzeichnis.addTab(tab, project_name)
            vLayout = QVBoxLayout(tab)
            vLayout.setAlignment(Qt.AlignTop)

            tab.zLabel = QLabel(str(timedelta(seconds=0)))

            vLayout.addWidget(tab.zLabel, 0, Qt.AlignTop)

            add_task_button = QPushButton("Neue Aufgabe hinzufügen")
            add_task_button.setShortcut("Ctrl+T")
            add_task_button.clicked.connect(lambda: self.new_task(project_name))

            vLayout.addWidget(add_task_button, 0, Qt.AlignTop)
            if self.project_format == "Flex_Grid":
                gLayout = FlowLayout()
            elif self.project_format == "Fix_Grid":
                gLayout = QGridLayout()

            gLayout.setAlignment(Qt.AlignTop)
            vLayout.addLayout(gLayout)

            tab.setLayout(vLayout)
            vLayout.gLayout = gLayout
            tab.vLayout = vLayout

            tab_timer.timeout.connect(lambda: self.summarize_time(tab))
            tab_timer.start(1000)

            self.project_dict[project_name]["tab"] = tab

    def new_task(self, project_name, task_name=None):
        if not task_name:
            task_name, ok = QInputDialog.getText(
                self, "Name der Aufgabe", "Tätigkeit", QLineEdit.Normal, "Neue Aufgabe"
            )
            if not ok:
                return
            if task_name in self.project_dict[project_name]["tasks"]:
                self.statusBar().showMessage(
                    "Es existiert bereits eine Aufgabe unter diesem Namen!"
                )
                return
            task_dict = {
                "id": None,
                "project_id": self.project_dict[project_name]["id"],
                "name": task_name,
                "started_at": datetime.now(),
                "ended_at": None,
                "time_slots": [],
                "task_obj": None,
                "count": 0,
            }
            task_dict["id"] = self.register_db_id("task", task_dict.copy())
            self.project_dict[project_name]["tasks"][task_name] = task_dict
        else:
            ok = True

        if ok:
            tab = self.project_dict[project_name]["tab"]

            task = QWidget()
            task.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            task.task_name = task_name
            task.project_name = project_name
            task_dict = self.project_dict[project_name]["tasks"][task.task_name]
            task.active_timer = {
                "started_at": None,
                "ended_at": None,
                "task_id": task_dict["id"],
                "count": 0,
            }
            self.project_dict[project_name]["tasks"][task_name]["task_obj"] = task

            task.flag = False
            task.count = task_dict["count"]

            task.timer = QTimer(task)
            verticalLayout = QVBoxLayout(task)
            horizontalLayout = QHBoxLayout()
            delete_task_button = QPushButton("Aufgabe löschen")
            delete_task_button.setStyleSheet("background-color : red;")
            push_button_start = QPushButton()
            push_button_stop = QPushButton()
            nLabel = QLabel(task_name)
            zLabel = QLabel(str(timedelta(seconds=task.count)))

            task.zLabel = zLabel

            verticalLayout.addWidget(nLabel, 0, Qt.AlignTop)
            verticalLayout.addWidget(zLabel, 0, Qt.AlignTop)

            push_button_start.setObjectName(u"start_timer")
            push_button_stop.setObjectName(u"stop_timer")
            push_button_start.setText("Start Timer")
            push_button_stop.setText("Stop Timer")

            delete_task_button.clicked.connect(lambda: self.delete_task(task))
            push_button_start.clicked.connect(
                lambda: self.start_stopwatch(task, project_name)
            )
            push_button_stop.clicked.connect(
                lambda: self.stop_stopwatch(task, project_name)
            )

            horizontalLayout.addWidget(push_button_start, 0, Qt.AlignBottom)
            horizontalLayout.addWidget(push_button_stop, 0, Qt.AlignBottom)

            verticalLayout.addLayout(horizontalLayout)
            verticalLayout.addWidget(delete_task_button, 0, Qt.AlignBottom)

            task.layout = verticalLayout
            task.setStyleSheet("background: rgba(239, 240, 241, 60);")

            task.timer.timeout.connect(lambda: self.showTime(task))
            task.timer.start(1000)

            tab.vLayout.gLayout.addWidget(task)
            # tab.vLayout.addWidget(task, 0, Qt.AlignTop)

    def about(self):
        QMessageBox.about(
            self,
            "About Time-Tracker",
            "<p>Anwendung zur Aufzeichnung der Arbeitszeit nach Projekten</p>"
            "<p>Powered by:</p>"
            "<p>- PyQt</p>"
            "<p>- Qt Designer</p>"
            "<p>- Python</p>",
        )


class DeleteDialog(QDialog):
    def __init__(self, item_name):
        super().__init__()

        self.setWindowTitle("HELLO!")

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        message = QLabel("Soll {} wirklich gelöscht werden?".format(item_name))
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())
