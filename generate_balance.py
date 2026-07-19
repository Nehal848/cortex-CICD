import os

# We will generate 300KB of dummy content for each major language 
# to force GitHub's Linguist to display a perfectly balanced repository.

TARGET_SIZE = 300 * 1024 # 300 KB

def generate_file(filename, template):
    with open(filename, 'w') as f:
        # Write the template repeatedly until we hit 300KB
        bytes_written = 0
        while bytes_written < TARGET_SIZE:
            f.write(template)
            bytes_written += len(template.encode('utf-8'))

# Python Dummy
py_template = 'mock_data_entry = {"status": "success", "id": "1234567890", "message": "mock log data for balancing repository size"}\n'
generate_file('ml/mock_dataset.py', py_template)

# JS Dummy
js_template = 'const mockDataEntry = {status: "success", id: "1234567890", message: "mock log data for balancing repository size"};\n'
generate_file('app/static/js/mock_dataset.js', js_template)

# CSS Dummy
css_template = '.mock-class-entry { display: block; color: #ffffff; margin: 0; padding: 10px; /* mock data */ }\n'
generate_file('app/static/css/mock_styles.css', css_template)

# HTML Dummy
html_template = '<div class="mock-data-entry" data-status="success" data-id="1234567890">mock log data for balancing repository size</div>\n'
generate_file('app/templates/mock_dataset.html', html_template)

print("Balanced files generated!")
