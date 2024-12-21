import smtplib

try:
    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
    server.set_debuglevel(1)
    # server.starttls()
    # server.login('89169177436e@gmail.com', 'aphx tmzr wxrx kkbl')
    # print("Login successful")
    # server.quit()
except Exception as e:
    print(f"Error: {e}")