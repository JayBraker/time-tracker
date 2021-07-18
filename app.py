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
import logging
#import BreezeStyleSheets
import pkg_resources
from main_view_ui import Ui_MainWindow
from flowlayout import FlowLayout
from datetime import datetime, timedelta

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        
        style_sheet = pkg_resources.resource_filename(__name__,'BreezeStyleSheets/dark.qss')
        style_sheet = pkg_resources.resource_filename(__name__,'dark.qss')
        #with open('BreezeStyleSheets/dark.qss') as fili: style_sheet = fili.read()
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
        
        self.setup_logging()
        
        if self.config.has_section("state"): # and 'file' in self.config['state']:
            if not "file" in self.config["state"] or not path.exists(self.config["state"]["file"]):
                self.open_file_dialog(True)

            self.database_file = self.config["state"].get("file")
            self.populate_from_db()

            if "auto_save" in self.config["state"]:
                save_interval = int(self.config["state"].get("auto_save"))
            else:
                save_interval = int(self.config["base_state"].get("auto_save"))
            self.auto_save = QTimer()
            self.auto_save.timeout.connect(lambda: self.write_state(by_ui_interaction=False))
            self.auto_save.start(int(save_interval))

        self.connectSignalsSlots()

    def setup_logging(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Setting up a log-file because of manual trigger.")
        if self.config.has_section("state") and not 'LOG_TO' in self.config["state"]:
            log_file, check = QFileDialog.getSaveFileName(
                None,
                "Speicherort für Log-Dateien auswählen",
                "",
                "Logfile (*.log)"
            )
            if check:
                self.config["state"]["LOG_TO"] = log_file
                
        if 'LOG_TO' in self.config["state"]:
            logging.basicConfig(format='%(asctime)s %(message)s', filename=self.config["state"]["LOG_TO"], level=logging.DEBUG)
            with open(self.config_file, "w") as conf:
                self.config.write(conf)
        else:
                        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)
        

    def open_file_dialog(self, new_file=False, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Open_File dialog for database because of manual trigger.")
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
                        logging.debug(table_statement)
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

    def clean_canvas(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Clearing UI Canvas because of manual trigger.")
        for project in self.project_dict:
            for task in self.project_dict[project]["tasks"]:
                self.delete_task(self.project_dict[project]["tasks"][task]["task_obj"],permanent=False)
            self.project_dict[project]["tab"].setParent(None)
            self.project_dict[project]["tab"].deleteLater()
        self.project_dict = {}
    
    def populate_from_db(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Started populating UI Canvas from database file because of manual trigger.")
        self.clean_canvas()
        if self.database_file:
            logging.debug("Attempting to load State from {}".format(self.database_file))
            projects_scheme = self.config["SCHEMES"].get("projects_scheme").split(", ")
            tasks_scheme = self.config["SCHEMES"].get("tasks_scheme").split(", ")
            with sqlite3.connect(self.database_file) as db:
                conn = db.cursor()
                try:
                    logging.debug("Loading Projects...")
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
                    logging.debug("Projects loaded.")
                except Exception as e:
                    logging.debug(e)
                try:
                    logging.debug("Loading tasks...")
                    for project in self.project_dict:
                        conn.execute(
                            "SELECT {keys} FROM tasks WHERE project_id = {pid};".format(
                                keys=", ".join(tasks_scheme),
                                pid=self.project_dict[project]["id"],
                            )
                        )
                        tasks_tuple = conn.fetchall()
                        logging.debug(tasks_tuple)
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
                            logging.debug("Loaded Task {}".format(task[2]))
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
                    logging.debug("All tasks loaded.")

                except Exception as e:
                    logging.debug(e)
            logging.debug("State fully loaded!")
            logging.debug("Project-Dict: {}".format(self.project_dict))
            self.draw_state()

    def draw_state(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Drawing fresh state on UI Canvas because of manual trigger.")
        for project in self.project_dict:
            logging.debug("Drawing {}".format(project))
            self.new_project(project)

            for task in self.project_dict[project]["tasks"]:
                logging.debug("Drawing {}".format(task))
                self.new_task(project, task)

    def write_state(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Writing current state of UI Canvas to database because of manual trigger.")
        logging.debug("Saving current state...")
        projects_scheme = self.config["SCHEMES"].get("projects_scheme").split(", ")
        tasks_scheme = self.config["SCHEMES"].get("tasks_scheme").split(", ")
        to_db = {"projects": [], "tasks": [], "timestamps": []}

        logging.debug("Compiling serializeable state.")
        for project in self.project_dict:
            logging.debug("Iterating projects...")
            temp_proj = {}
            for key in projects_scheme:
                if key in self.project_dict[project]:
                    temp_proj[key] = self.project_dict[project][key]
                else:
                    temp_proj[key] = ""
            to_db["projects"].append(temp_proj)
            
            logging.debug("Iterating Tasks for project {}...".format(project))
            for task in self.project_dict[project]["tasks"]:
                self.save_timer(task=self.project_dict[project]["tasks"][task]["task_obj"], project_name=project, auto_save=True)               
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

    def connectSignalsSlots(self, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Connecting Signalslots because of manual trigger.")
        self.action_about.triggered.connect(lambda: self.about(by_ui_interaction=True))
        self.action_new_projekt.triggered.connect(lambda: self.new_project(by_ui_interaction=True))
        self.action_open_file.triggered.connect(lambda: self.open_file_dialog(False, by_ui_interaction=True))
        self.action_new.triggered.connect(lambda: self.open_file_dialog(True, by_ui_interaction=True))

    def closeEvent(self, event, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Executing CloseEvents because of manual trigger.")
        logging.debug("Saving state...")
        self.write_state()
        logging.debug("Finished!")
        self.close

    def register_db_id(self, type: str, object_dict, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Registering new item in database because of manual trigger:\n  Type: {}\n  JSON: {}".format(type, object_dict))
        if not path.isfile(self.database_file):
            dlg = GeneralDialog(info_txt='Aktuell ist keine Datenbank geöffnet.\nBitte öffne erst eine Datenbank oder lege eine neue Datei an.', info=True, title='Kann kein Projekt anlegen')
            if dlg.exec():
                return
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
            logging.debug(sql_insert)
            cursor.execute(sql_insert)
            cursor.execute(
                "SELECT id FROM {} WHERE name = '{}';".format(type, object_dict["name"])
            )
            id = cursor.fetchone()[0]

            return id

    def showTime(self, task, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Refreshing timecounter for Task {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
        # checking if flag is true
        if task.flag:
            task.count += 1
        text = str(timedelta(seconds=task.count))
        task.zLabel.setText(text)

    def start_stopwatch(self, task, project_name, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Started timecounter for Task {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
        task.flag = True
        task.active_timer["started_at"] = datetime.now()

    def save_timer(self, task, project_name, by_ui_interaction=False, auto_save=False):
        if by_ui_interaction:
            logging.debug("Saved count of timer for task  {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
        if task.flag:
            timer = task.active_timer.copy()
            timer["ended_at"] = datetime.now()
            delta = timer["ended_at"] - timer["started_at"]
            timer["count"] = delta.total_seconds()

            task_dict = self.project_dict[project_name]["tasks"][task.task_name]
            task_dict["time_slots"].append(timer)
            task.active_timer = {
                "started_at": None,
                "ended_at": None,
                "task_id": task_dict["id"],
                "count": 0,
            }
            if auto_save:
                task.active_timer["started_at"] = timer["ended_at"]
        return

    def stop_stopwatch(self, task, project_name, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Stopped timecounter for Task {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
        if task.flag:
            self.save_timer(task, project_name, by_ui_interaction=False, auto_save=False)
            task.flag = False
        return

    def delete_task(self, task, permanent=True, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Deleted Task {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
        if task.flag:
            self.stop_stopwatch(task, task.project_name)
        if permanent:
            dlg = DeleteDialog(task.task_name)
            if dlg.exec():
                logging.debug("Removing Task {} from database!".format(task.task_name))
                logging.debug(task.parent().vLayout.gLayout.removeWidget(task))
                task_id = self.project_dict[task.project_name]["tasks"][task.task_name][
                    "id"
                ]
                self.project_dict[task.project_name]["tasks"].pop(task.task_name)
                with sqlite3.connect(self.database_file) as db:
                    cursor = db.cursor()
                    cursor.execute("DELETE FROM tasks WHERE id = {}".format(task_id))
            else:
                return

        task.deleteLater()

    def summarize_time(self, tab, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Summarizing timecounter for Task {} of Project {} because of manual trigger.".format(task.task_name, task.project_name))
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

    def new_project(self, project_name=None, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Creating new Project {} because of manual trigger.".format(project_name))

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
            logging.debug("Project {} received internal ID {}.".format(project_name, project_dict["id"]))
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
            add_task_button.clicked.connect(lambda: self.new_task(project_name, by_ui_interaction=True))

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

            tab_timer.timeout.connect(lambda: self.summarize_time(tab, by_ui_interaction=False))
            tab_timer.start(1000)

            self.project_dict[project_name]["tab"] = tab

    def new_task(self, project_name, task_name=None, by_ui_interaction=False):
        if by_ui_interaction:
            logging.debug("Creating NEW Task for Project {} because of manual trigger.".format(project_name))
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
            logging.debug("New Tasks name: {}".format(task_name))
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

            delete_task_button.clicked.connect(lambda: self.delete_task(task, by_ui_interaction=True))
            push_button_start.clicked.connect(
                lambda: self.start_stopwatch(task, project_name, by_ui_interaction=True)
            )
            push_button_stop.clicked.connect(
                lambda: self.stop_stopwatch(task, project_name, by_ui_interaction=True)
            )

            horizontalLayout.addWidget(push_button_start, 0, Qt.AlignBottom)
            horizontalLayout.addWidget(push_button_stop, 0, Qt.AlignBottom)

            verticalLayout.addLayout(horizontalLayout)
            verticalLayout.addWidget(delete_task_button, 0, Qt.AlignBottom)

            task.layout = verticalLayout
            task.setStyleSheet("background: rgba(239, 240, 241, 60);")

            task.timer.timeout.connect(lambda: self.showTime(task, by_ui_interaction=False))
            task.timer.start(1000)

            tab.vLayout.gLayout.addWidget(task)
            # tab.vLayout.addWidget(task, 0, Qt.AlignTop)

    def about(self, by_ui_interaction=False):
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

        self.setWindowTitle("Löschdialog")

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        message = QLabel("Soll {} wirklich gelöscht werden?".format(item_name))
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

class GeneralDialog(QDialog):
    def __init__(self, info_txt, info=True, item_name=None, title="Hallo!"):
        super().__init__()

        self.setWindowTitle(title)

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        if not info_txt:
            self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        text = info
        if item_name:
            text.format(item_name)
        message = QLabel(item)
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())
