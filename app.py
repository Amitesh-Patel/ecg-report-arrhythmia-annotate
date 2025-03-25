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


def get_pdf_files(directory="/home/amiteshpatel/Desktop/Arrythmia_Annotator/Data_19_March"):
    if not os.path.exists(directory):
        os.makedirs(directory)
        st.info(f"Created directory '{directory}'. Please add ECG PDFs to this folder.")
        return []

    return [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]


def display_pdf(pdf_path):
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")

    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'

    st.markdown(pdf_display, unsafe_allow_html=True)


def save_annotation(pdf_filename, selected_arrhythmias, custom_arrhythmia, notes):
    annotations_dir = "annotations"
    if not os.path.exists(annotations_dir):
        os.makedirs(annotations_dir)

    all_arrhythmias = selected_arrhythmias.copy()
    if custom_arrhythmia:
        all_arrhythmias.append(custom_arrhythmia)

    annotation_data = {
        "filename": pdf_filename,
        "arrhythmias": all_arrhythmias,
        "notes": notes,
        "annotated_by": st.session_state.get("doctor_name", "Unknown"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    json_filename = os.path.splitext(pdf_filename)[0] + ".json"
    json_path = os.path.join(annotations_dir, json_filename)

    with open(json_path, "w") as f:
        json.dump(annotation_data, f, indent=4)

    return json_path


def load_annotation(pdf_filename):
    json_filename = os.path.splitext(pdf_filename)[0] + ".json"
    json_path = os.path.join("annotations", json_filename)

    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
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

        pdf_files = get_pdf_files()

        if not pdf_files:
            st.warning("No PDF files found. Please add ECG PDFs to the 'ecg_pdfs' folder.")
            return

        if "current_pdf_idx" not in st.session_state:
            st.session_state.current_pdf_idx = 0

        col1, col2, col3, col4 = st.columns([1, 1, 3, 1])

        with col1:
            if st.button("⬅️ Previous"):
                st.session_state.current_pdf_idx = max(0, st.session_state.current_pdf_idx - 1)
                st.rerun()

        with col2:
            if st.button("Next ➡️"):
                st.session_state.current_pdf_idx = min(
                    len(pdf_files) - 1, st.session_state.current_pdf_idx + 1
                )
                st.rerun()

        with col3:
            st.write(f"File {st.session_state.current_pdf_idx + 1} of {len(pdf_files)}")

        with col4:
            jump_to = st.selectbox(
                "Jump to file", options=pdf_files, index=st.session_state.current_pdf_idx
            )
            if jump_to != pdf_files[st.session_state.current_pdf_idx]:
                st.session_state.current_pdf_idx = pdf_files.index(jump_to)
                st.rerun()

        current_pdf = pdf_files[st.session_state.current_pdf_idx]
        current_pdf_path = os.path.join(
            "/home/amiteshpatel/Desktop/Arrythmia_Annotator/Data_19_March", current_pdf
        )

        st.header(f"ECG Report: {current_pdf}")
        display_pdf(current_pdf_path)

        existing_annotation = load_annotation(current_pdf)

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
                json_path = save_annotation(
                    current_pdf, selected_arrhythmias, custom_arrhythmia, notes
                )
                st.success(f"Annotation saved successfully to {json_path}")

        if existing_annotation:
            with st.expander("View Annotation History"):
                st.json(existing_annotation)

    with tab2:
        handle_file_upload()


if __name__ == "__main__":
    main()
