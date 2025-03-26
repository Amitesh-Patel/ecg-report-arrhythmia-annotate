import streamlit as st
import os
import json
import base64
from datetime import datetime
import pandas as pd
from PyPDF2 import PdfReader
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import io
import zipfile
from streamlit_pdf_viewer import pdf_viewer

# https://github.com/lfoppiano/streamlit-pdf-viewer

st.set_page_config(page_title="ECG Arrhythmia Annotator", layout="wide")

ARRHYTHMIA_OPTIONS = [
    "Atrial Fibrillation",
    "Atrial Flutter",
    "Ventricular Tachycardia",
    "Ventricular Fibrillation",
    "Premature Ventricular Contraction (PVC)",
    "Premature Atrial Contraction (PAC)",
    "Sinus Bradycardia",
    "Sinus Tachycardia",
    "First-degree AV Block",
    "Second-degree AV Block",
    "Third-degree AV Block",
    "Bundle Branch Block",
    "Supraventricular Tachycardia (SVT)",
    "Junctional Rhythm",
    "Asystole",
]

AZURE_STORAGE_CONNECTION_STRING = st.secrets.get("AZURE_STORAGE_CONNECTION_STRING", "")
CONTAINER_NAME = "ecg-report-app-database"


def initialize_blob_storage():
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        # Create container if it doesn't exist
        if not container_client.exists():
            container_client.create_container()

        return blob_service_client, container_client
    except Exception as e:
        st.error(f"Azure Blob Storage initialization error: {e}")
        return None, None


def upload_to_azure_blob(file, blob_service_client):
    try:
        # Create a blob client
        blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=file.name)

        # Reset file pointer to the beginning
        file.seek(0)

        # Read the entire file content
        file_content = file.read()

        # Upload the file content
        blob_client.upload_blob(file_content, overwrite=True)
        return True
    except Exception as e:
        st.error(f"Error uploading {file.name} to Azure Blob Storage: {e}")
        return False


def process_pdf_file(file):
    # Basic PDF validation
    try:
        pdf_reader = PdfReader(file)
        print(pdf_reader)
        return True
    except:
        return False


def handle_file_upload():
    st.header("PDF File Upload")

    # Initialize Azure Blob Storage
    blob_service_client, container_client = initialize_blob_storage()

    if not blob_service_client:
        st.error("Azure Blob Storage connection failed. Please check your configuration.")
        return

    # File upload section
    uploaded_files = st.file_uploader(
        "Choose PDF files or a ZIP file containing PDFs",
        type=["pdf", "zip"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        successful_uploads = []
        failed_uploads = []

        for file in uploaded_files:
            # Check if it's a ZIP file
            if file.name.lower().endswith(".zip"):
                with zipfile.ZipFile(file, "r") as z:
                    # Extract and process PDF files from ZIP
                    pdf_files = [f for f in z.namelist() if f.lower().endswith(".pdf")]

                    for pdf_filename in pdf_files:
                        with z.open(pdf_filename) as pdf_file:
                            pdf_bytes = pdf_file.read()
                            pdf_io = io.BytesIO(pdf_bytes)
                            pdf_io.name = pdf_filename  # Set the filename

                            # Validate PDF
                            if process_pdf_file(pdf_io):
                                # Upload to Azure Blob Storage
                                if upload_to_azure_blob(pdf_io, blob_service_client):
                                    successful_uploads.append(pdf_filename)
                                else:
                                    failed_uploads.append(pdf_filename)
            else:
                # Single PDF file upload
                if process_pdf_file(file):
                    if upload_to_azure_blob(file, blob_service_client):
                        successful_uploads.append(file.name)
                    else:
                        failed_uploads.append(file.name)

        # Display upload results
        if successful_uploads:
            st.success(f"Successfully uploaded {len(successful_uploads)} files:")
            for filename in successful_uploads:
                st.write(f"- {filename}")

        if failed_uploads:
            st.warning(f"Failed to upload {len(failed_uploads)} files:")
            for filename in failed_uploads:
                st.write(f"- {filename}")


def get_pdf_files_from_blob():
    try:
        blob_service_client, container_client = initialize_blob_storage()

        if not container_client:
            st.error("Could not initialize blob storage")
            return []

        # List all blobs in the container
        blob_list = container_client.list_blobs()

        # Filter only PDF files
        pdf_files = [blob.name for blob in blob_list if blob.name.lower().endswith(".pdf")]

        return pdf_files
    except Exception as e:
        st.error(f"Error retrieving PDF files: {e}")
        return []


def download_pdf_from_blob(pdf_filename):
    try:
        blob_service_client, container_client = initialize_blob_storage()

        if not container_client:
            st.error("Could not initialize blob storage")
            return None

        # Get blob client
        blob_client = container_client.get_blob_client(pdf_filename)

        # Download blob content
        pdf_bytes = blob_client.download_blob().readall()

        return pdf_bytes
    except Exception as e:
        st.error(f"Error downloading PDF {pdf_filename}: {e}")
        return None


def display_pdf_from_blob(pdf_filename):
    try:
        # Download PDF bytes from blob storage
        pdf_bytes = download_pdf_from_blob(pdf_filename)

        if pdf_bytes:
            # Use streamlit-pdf-viewer to display PDF
            pdf_viewer(input=pdf_bytes, width=1400)
        else:
            st.error(f"Could not retrieve PDF: {pdf_filename}")
    except Exception as e:
        st.error(f"Error displaying PDF: {e}")


def save_annotation_to_blob(pdf_filename, annotation_data):
    try:
        blob_service_client, container_client = initialize_blob_storage()

        if not container_client:
            st.error("Could not initialize blob storage")
            return None

        # Create JSON filename
        json_filename = os.path.splitext(pdf_filename)[0] + ".json"

        # Get blob client for JSON
        blob_client = container_client.get_blob_client(json_filename)

        # Convert annotation to JSON
        json_data = json.dumps(annotation_data, indent=4)

        # Upload JSON to blob
        blob_client.upload_blob(json_data, overwrite=True)

        return json_filename
    except Exception as e:
        st.error(f"Error saving annotation: {e}")
        return None


def load_annotation_from_blob(pdf_filename):
    try:
        blob_service_client, container_client = initialize_blob_storage()

        if not container_client:
            st.error("Could not initialize blob storage")
            return None

        # Create JSON filename
        json_filename = os.path.splitext(pdf_filename)[0] + ".json"

        # Check if JSON blob exists
        blob_client = container_client.get_blob_client(json_filename)

        if blob_client.exists():
            # Download JSON content
            json_content = blob_client.download_blob().readall().decode("utf-8")

            # Parse JSON
            return json.loads(json_content)

        return None
    except Exception as e:
        st.error(f"Error loading annotation: {e}")
        return None


def main():
    st.title("ECG Arrhythmia Annotator")
    tab1, tab2 = st.tabs(["Annotation", "File Upload"])
    with tab1:
        with st.sidebar:
            st.header("Doctor Information")
            doctor_name = st.text_input(
                "Doctor Name", key="doctor_name", value=st.session_state.get("doctor_name", "")
            )
            st.divider()

            st.header("Annotation Statistics")
            if os.path.exists("annotations"):
                annotation_files = [f for f in os.listdir("annotations") if f.endswith(".json")]
                st.write(f"Total annotated: {len(annotation_files)}")

                if annotation_files:
                    st.write("Recently annotated:")
                    for idx, file in enumerate(sorted(annotation_files, reverse=True)[:5]):
                        st.write(f"{idx+1}. {file}")

        pdf_files = get_pdf_files_from_blob()

        if not pdf_files:
            st.warning("No PDF files found. Please add ECG PDFs to the 'ecg_pdfs' folder.")
            return

        current_pdf_idx = st.session_state.get("current_pdf_idx", 0)

        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            st.write(f"File {current_pdf_idx + 1} of {len(pdf_files)}")

        with col2:
            jump_to = st.selectbox("Jump to file", options=pdf_files, index=current_pdf_idx)
            if jump_to != pdf_files[current_pdf_idx]:
                current_pdf_idx = pdf_files.index(jump_to)
                st.session_state.current_pdf_idx = current_pdf_idx

        current_pdf = pdf_files[current_pdf_idx]
        st.header(f"ECG Report: {current_pdf}")
        display_pdf_from_blob(current_pdf)

        existing_annotation = load_annotation_from_blob(current_pdf)

        st.header("Arrhythmia Annotation")

        default_selections = existing_annotation["arrhythmias"] if existing_annotation else []
        default_selections = [a for a in default_selections if a in ARRHYTHMIA_OPTIONS]

        selected_arrhythmias = st.multiselect(
            "Select arrhythmia types:", options=ARRHYTHMIA_OPTIONS, default=default_selections
        )

        custom_default = (
            next((a for a in existing_annotation["arrhythmias"] if a not in ARRHYTHMIA_OPTIONS), "")
            if existing_annotation
            else ""
        )
        custom_arrhythmia = st.text_input(
            "Other arrhythmia (if not in the list):", value=custom_default
        )

        notes_default = existing_annotation["notes"] if existing_annotation else ""
        notes = st.text_area("Additional notes:", value=notes_default)

        if st.button("Save Annotation"):
            if not doctor_name:
                st.error("Please enter your name before saving annotations.")
            elif not (selected_arrhythmias or custom_arrhythmia):
                st.error("Please select at least one arrhythmia or enter a custom one.")
            else:
                all_arrhythmias = selected_arrhythmias.copy()
                if custom_arrhythmia:
                    all_arrhythmias.append(custom_arrhythmia)
                annotation_data = {
                    "filename": current_pdf,
                    "arrhythmias": all_arrhythmias,
                    "notes": notes,
                    "annotated_by": st.session_state.get("doctor_name", "Unknown"),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                json_path = save_annotation_to_blob(current_pdf, annotation_data)
                st.success(f"Annotation saved successfully to {json_path}")

        if existing_annotation:
            with st.expander("View Annotation History"):
                st.json(existing_annotation)

        col_prev, col_next = st.columns([1, 1])

        with col_prev:
            if st.button("⬅️ Previous"):
                current_pdf_idx = max(0, current_pdf_idx - 1)
                st.session_state.current_pdf_idx = current_pdf_idx

        with col_next:
            if st.button("Next ➡️"):
                current_pdf_idx = min(len(pdf_files) - 1, current_pdf_idx + 1)
                st.session_state.current_pdf_idx = current_pdf_idx

    with tab2:
        handle_file_upload()


if __name__ == "__main__":
    main()
