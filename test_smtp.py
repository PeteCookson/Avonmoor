import smtplib

try:
    server = smtplib.SMTP('smtp.ionos.co.uk', 587)  # Change this if you're using a different SMTP server
    server.starttls()
    server.login('hello@avonmoor.co.uk', 'jyssoS-pofruz-vehwo0')  # Replace with your email and password
    print("Login successful")
    server.quit()
except smtplib.SMTPAuthenticationError as e:
    print(f"SMTP Authentication Error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")