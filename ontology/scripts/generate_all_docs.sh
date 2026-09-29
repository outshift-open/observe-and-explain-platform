#!/bin/bash
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

# Local test script for documentation generation

set -e

echo "🧹 Cleaning previous builds..."
rm -rf docs/ test-widoco/

echo "📁 Creating directory structure..."
mkdir -p docs/comprehensive
mkdir -p docs/widoco
mkdir -p docs/webvowl/data
mkdir -p docs/lode

# Download Widoco JAR if not present
if [ ! -f "widoco.jar" ]; then
  echo "📦 Downloading Widoco JAR (JDK 17 version)..."
  wget -O widoco.jar https://github.com/dgarijo/Widoco/releases/download/v1.4.25/widoco-1.4.25-jar-with-dependencies_JDK-17.jar
  echo "✅ Downloaded widoco.jar"
fi

echo "📝 Generating Widoco Documentation..."
java -jar widoco.jar \
  -ontFile src/oxp_ontology/mas-ontology.ttl \
  -outFolder docs/widoco \
  -rewriteAll \
  -includeAnnotationProperties \
  -webVowl \
  -htaccess \
  -licensius

# Create index.html redirect since Widoco generates index-en.html
echo '<meta http-equiv="refresh" content="0; url=index-en.html">' > docs/widoco/index.html
echo "✅ Widoco docs: docs/widoco/index-en.html"

echo "📝 Generating WebVOWL Documentation..."

# Build WebVOWL if not already built
if [ ! -d "docs/webvowl/js" ]; then
  echo "📦 Building WebVOWL..."
  wget -q https://github.com/VisualDataWeb/WebVOWL/archive/refs/tags/1.1.6.tar.gz
  tar -xzf 1.1.6.tar.gz
  cd WebVOWL-1.1.6
  
  # Change default ontology from foaf to mas-ontology BEFORE building
  sed -i '' 's/DEFAULT_JSON_NAME = "foaf"/DEFAULT_JSON_NAME = "mas-ontology"/g' src/app/js/loadingModule.js
  
  npm install --silent
  npm run release --silent
  cd ..
  mkdir -p docs/webvowl
  cp -r WebVOWL-1.1.6/deploy/* docs/webvowl/
  rm -rf WebVOWL-1.1.6 1.1.6.tar.gz
  echo "✅ WebVOWL built"
fi

# Generate ontology JSON
python3 scripts/generate_webvowl_json.py
echo "✅ WebVOWL: docs/webvowl/index.html"


echo "📝 Generating LODE Documentation..."
python3 scripts/generate_lode_html.py
echo "✅ LODE: docs/lode/index.html"

echo "📝 Creating landing page..."
cat > docs/index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAS Ontology Documentation</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #24292f;
            background: #f6f8fa;
            padding: 40px 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 60px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        h1 {
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 16px;
            color: #0969da;
        }
        .subtitle {
            font-size: 20px;
            color: #57606a;
            margin-bottom: 40px;
            line-height: 1.5;
        }
        .docs-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
            margin-top: 48px;
        }
        .doc-card {
            border: 2px solid #d0d7de;
            border-radius: 8px;
            padding: 28px;
            transition: all 0.2s;
            text-decoration: none;
            color: inherit;
            display: block;
        }
        .doc-card:hover {
            border-color: #0969da;
            box-shadow: 0 6px 16px rgba(9, 105, 218, 0.15);
            transform: translateY(-2px);
        }
        .doc-card h2 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 12px;
            color: #0969da;
        }
        .doc-card p {
            font-size: 15px;
            color: #57606a;
            line-height: 1.6;
        }
        .doc-card .badge {
            display: inline-block;
            background: #ddf4ff;
            color: #0969da;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .about {
            background: #f6f8fa;
            padding: 24px;
            border-radius: 8px;
            margin-bottom: 32px;
        }
        .about h3 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 12px;
        }
        .about p {
            font-size: 15px;
            color: #57606a;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 MAS Ontology</h1>
        <div class="subtitle">
            Multi-Agent System Telemetry Ontology for comprehensive MAS governance and observability
        </div>
        
        <div class="about">
            <h3>About This Ontology</h3>
            <p>
                The MAS Ontology provides a structured knowledge representation for Multi-Agent Systems,
                capturing structural components, execution traces, state trajectories, and governance metrics.
                Built on OpenTelemetry standards, it enables deep observability and evaluation of agent behaviors.
            </p>
        </div>
        
        <h2 style="font-size: 28px; margin-bottom: 20px; color: #24292f;">📚 Documentation Formats</h2>
        
        <div class="docs-grid">
            <a href="custom/" class="doc-card">
                <h2>Custom Documentation</h2>
                <p>
                    OCSF-style comprehensive documentation with hierarchical blocks, 
                    interactive visualizations, concrete examples, and complete relationship mappings.
                </p>
                <span class="badge">Recommended</span>
            </a>
            
            <a href="webvowl/" class="doc-card">
                <h2>WebVOWL</h2>
                <p>
                    Interactive graph visualization with zoom, filtering, and exploration.
                    Perfect for understanding the complete ontology structure visually.
                </p>
                <span class="badge">Interactive</span>
            </a>
            
            <a href="widoco/index-en.html" class="doc-card">
                <h2>Widoco</h2>
                <p>
                    Standard OWL documentation with cross-references, namespace details,
                    and W3C-compliant structure. Industry-standard format.
                </p>
                <span class="badge">Standard</span>
            </a>
            
            <a href="lode/" class="doc-card">
                <h2>LODE</h2>
                <p>
                    Live OWL Documentation Environment. Lightweight, clean HTML
                    documentation with minimal styling and fast loading.
                </p>
                <span class="badge">Lightweight</span>
            </a>
        </div>
        
        <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #d0d7de; text-align: center; color: #57606a; font-size: 14px;">
            <p>Generated from <code>src/oxp_ontology/mas-ontology.ttl</code> • View on <a href="https://github.com/outshift-open/observe-and-explain-platform/ontology" style="color: #0969da;">GitHub</a></p>
        </div>
    </div>
</body>
</html>
EOF

echo "✅ Landing page: docs/index.html"

echo ""
echo "🎉 All documentation generated successfully!"
echo ""
echo "📂 Output structure:"
echo "   docs/"
echo "   ├── index.html (landing page)"
echo "   ├── ocsf/ (OCSF-style docs)"
echo "   ├── widoco/ (standard OWL docs)"
echo "   ├── webvowl/ (interactive graph)"
echo "   └── lode/ (lightweight docs)"
echo ""
echo "🌐 To serve locally:"
echo "   python3 -m http.server 8000 --directory docs"
echo "   Open: http://localhost:8000"
