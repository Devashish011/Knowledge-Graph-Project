import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from queue import Queue
from neo4j_uploader import Neo4jUploader, process_csv_and_upload
from neo4j import GraphDatabase

class CSVToNeo4jUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV to Neo4j Uploader")
        self.root.geometry("600x450")
        
        self.csv_filename = ""
        self.df = None
        self.neo4j_uploader = None
        self.queue = Queue()  # Queue for updating UI

        self.create_ui()
        self.update_status_box()  # Start status box updates

    def create_ui(self):
        frame = tk.Frame(self.root)
        frame.pack(pady=10)
        
        # Neo4j Connection Details
        tk.Label(frame, text="Neo4j URI:").grid(row=0, column=0)
        self.uri_entry = tk.Entry(frame, width=40)
        self.uri_entry.grid(row=0, column=1)
        self.uri_entry.insert(0, "bolt://localhost:7687")
        
        tk.Label(frame, text="Username:").grid(row=1, column=0)
        self.username_entry = tk.Entry(frame, width=40)
        self.username_entry.grid(row=1, column=1)
        self.username_entry.insert(0, "neo4j")
        
        tk.Label(frame, text="Password:").grid(row=2, column=0)
        self.password_entry = tk.Entry(frame, width=40, show="*")
        self.password_entry.grid(row=2, column=1)
        
        tk.Label(frame, text="Database:").grid(row=3, column=0)
        self.database_entry = tk.Entry(frame, width=40)
        self.database_entry.grid(row=3, column=1)
        self.database_entry.insert(0, "neo4j")

        # Buttons
        self.test_connection_button = tk.Button(self.root, text="Test Connection", command=self.test_connection)
        self.test_connection_button.pack(pady=5)
        
        self.select_file_button = tk.Button(self.root, text="Select CSV File", command=self.select_file)
        self.select_file_button.pack(pady=5)
        
        self.upload_button = tk.Button(self.root, text="Upload to Neo4j", command=self.upload_data, state=tk.DISABLED)
        self.upload_button.pack(pady=5)
        
        # Progress Bar
        self.progress = ttk.Progressbar(self.root, orient=tk.HORIZONTAL, length=300, mode='determinate')
        self.progress.pack(pady=5)

        # Status Box
        self.status_box = tk.Text(self.root, height=10, width=70, state=tk.DISABLED)
        self.status_box.pack(pady=5)
    
    def test_connection(self):
        """Tests the connection to Neo4j."""
        uri = self.uri_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        database = self.database_entry.get()
        
        try:
            driver = GraphDatabase.driver(uri, auth=(username, password))
            with driver.session(database=database) as session:
                session.run("RETURN 1")  # Simple test query
            driver.close()
            self.queue.put("Connected Successfully")
        except Exception as e:
            self.queue.put(f"Connection Failed : {str(e)}")

    def select_file(self):
        """Opens a file dialog to select a CSV file."""
        self.csv_filename = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if self.csv_filename:
            self.queue.put(f"Selected CSV: {self.csv_filename}")
            self.upload_button.config(state=tk.NORMAL)

    def upload_data(self):
        """Starts the Neo4j upload process in a separate thread."""
        self.queue.put("Starting upload...")
        
        self.neo4j_uploader = Neo4jUploader(
            self.uri_entry.get(), self.username_entry.get(),
            self.password_entry.get(), self.database_entry.get()
        )
        
        thread = threading.Thread(target=self.process_upload, daemon=True)
        thread.start()

    def process_upload(self):
        """Processes CSV upload in a background thread."""
        try:
            process_csv_and_upload(self.csv_filename, self.neo4j_uploader)
            self.queue.put("Upload complete!")
        except Exception as e:
            self.queue.put(f"Error: {str(e)}")

    def update_status_box(self):
        """Continuously updates the status box with messages from the queue."""
        while not self.queue.empty():
            msg = self.queue.get()
            self.status_box.config(state=tk.NORMAL)
            self.status_box.insert(tk.END, msg + "\n")
            self.status_box.config(state=tk.DISABLED)
            self.status_box.yview(tk.END)
        self.root.after(100, self.update_status_box)  # Refresh UI every 100ms

def main():
    root = tk.Tk()
    app = CSVToNeo4jUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
