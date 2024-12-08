from app import app
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Heroku provides the PORT, locally defaults to 5000
    app.run(debug=True, host="0.0.0.0", port=port)
