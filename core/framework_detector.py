from pydantic import BaseModel
from typing import Dict, Any

class IntegrationSnippet(BaseModel):
    integration_code: str
    instructions: str

class IntegrationResponse(BaseModel):
    framework: str
    language: str
    integration_type: str
    integration_code: str
    instructions: str

class DefaultIntegrationsResponse(BaseModel):
    error: str
    default_integrations: Dict[str, str]

def detect_framework(html: str):
    """Enhanced framework detection for various frontend frameworks"""
    html_lower = html.lower()
    
    # React and Next.js
    if "react" in html_lower or "root" in html_lower or "next/data" in html_lower or "__next" in html_lower:
        return "React/Next.js", "js"
    
    # Vue.js and Nuxt.js
    elif "vue" in html_lower or "v-bind" in html_lower or "nuxt" in html_lower or "__nuxt" in html_lower:
        return "Vue/Nuxt.js", "js"
    
    # Angular
    elif "angular" in html_lower or "ng-" in html_lower:
        return "Angular", "js"
    
    # Svelte and SvelteKit
    elif "svelte" in html_lower:
        return "Svelte/SvelteKit", "js"
    
    # jQuery and traditional JS
    elif "jquery" in html_lower or "$(" in html_lower:
        return "jQuery", "js"
    
    # WordPress
    elif "wp-content" in html_lower or "wordpress" in html_lower:
        return "WordPress", "js"
    
    # Django templates
    elif "{% block content %}" in html_lower or "django" in html_lower:
        return "Django", "js"
    
    # Flask/Jinja templates
    elif "flask" in html_lower or "jinja" in html_lower:
        return "Flask/Jinja", "js"
    
    # Spring/Java
    elif "spring" in html_lower or "thymeleaf" in html_lower:
        return "Spring/Thymeleaf", "js"
    
    # Laravel/PHP
    elif "laravel" in html_lower or "php" in html_lower:
        return "Laravel/PHP", "js"
    
    # Static HTML with modern JS frameworks
    elif "module" in html_lower or "import" in html_lower or "export" in html_lower:
        return "Modern JavaScript", "js"
    
    # Default fallback
    return "HTML/CSS/JS", "js"

def generate_snippet(framework, bot_id="42", api_key="USER_API_KEY", bot_name="AI Assistant") -> IntegrationSnippet:
    """Generate integration snippets for various frontend frameworks"""
    
    base_js_snippet = f"""
<!-- Chatbot Integration Snippet -->
<script>
(function(){{
  var s = document.createElement("script");
  s.src = "http://127.0.0.1:8000/static/chatbot.js?bot_id={bot_id}&api_key={api_key}&bot_name={bot_name.replace(' ', '+')}";
  document.body.appendChild(s);
}})();
</script>
<!-- End Chatbot Integration -->
"""
    
    snippets = {
        "React/Next.js": IntegrationSnippet(
            integration_code=f"""
// For React/Next.js - Add this component to your app
import {{ useEffect }} from "react";

export default function ChatbotWidget() {{
  useEffect(() => {{
    const s = document.createElement("script");
    s.src = "http://127.0.0.1:8000/static/chatbot.js?bot_id={bot_id}&api_key={api_key}&bot_name={bot_name.replace(' ', '+')}";
    document.body.appendChild(s);
    
    return () => {{
      // Cleanup if component unmounts
      const existingScript = document.querySelector('script[src*="chatbot.js"]');
      if (existingScript) {{
        existingScript.remove();
      }}
    }};
  }}, []);

  return null;
}}

// Usage: Import and use <ChatbotWidget /> in your main App component
""",
            instructions="Import ChatbotWidget in your App.js, _app.js (Next.js), or main layout component and render it near the root level."
        ),
        
        "Vue/Nuxt.js": IntegrationSnippet(
            integration_code=f"""
<!-- For Vue.js - Add this component -->
<template>
  <div><!-- Chatbot will be injected here --></div>
</template>

<script>
export default {{
  name: 'ChatbotWidget',
  mounted() {{
    const s = document.createElement("script");
    s.src = "http://127.0.0.1:8000/static/chatbot.js?bot_id={bot_id}&api_key={api_key}&bot_name={bot_name.replace(' ', '+')}";
    document.body.appendChild(s);
  }},
  beforeUnmount() {{
    const existingScript = document.querySelector('script[src*="chatbot.js"]');
    if (existingScript) {{
      existingScript.remove();
    }}
  }}
}}
</script>

<!-- For Nuxt.js, place this in layouts/default.vue or create a plugin -->
""",
            instructions="Register the ChatbotWidget component in your main Vue app or add it to your Nuxt.js layout."
        )
    }
    
    # Return framework-specific snippet or default HTML/JS
    if framework in snippets:
        return snippets[framework]
    else:
        # Default HTML/CSS/JS snippet
        return IntegrationSnippet(
            integration_code=base_js_snippet,
            instructions="Paste this code before the closing </body> tag on all pages where you want the chatbot to appear."
        )

def default_integrations() -> DefaultIntegrationsResponse:
    """Return default integration templates for HTML/JS and React"""
    return DefaultIntegrationsResponse(
        error="Crawling not possible for this website. Returning default integration templates.",
        default_integrations={
            "html_js": generate_snippet("HTML/CSS/JS").integration_code,
            "react": generate_snippet("React/Next.js").integration_code
        }
    )