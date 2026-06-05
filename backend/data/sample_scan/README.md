# Sample Scan Storage

This folder simulates object storage such as S3.

The backend writes fake scan files here when `POST /scans` is called. The app
uses generated PNG slices for learning, so no real patient data belongs here.
