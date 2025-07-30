import customtkinter as ctk
import tkinter as tk
from openai import OpenAI
import threading
import re
import time

# App Config
ctk.set_appearance_mode("Dark")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")

# --- DeepSeek/OpenRouter API Setup ---
API_KEY = "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"
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

# List of common study subjects
COMMON_SUBJECTS = [
    "c++", "python", "java", "javascript", "html", "css", "physics", "math", "mathematics", "biology", "chemistry", "english", "history", "geography", "science", "algebra", "geometry", "calculus", "statistics", "literature", "economics", "philosophy", "art", "music", "computer science", "programming", "sql", "networking", "machine learning", "ai", "artificial intelligence", "data science", "french", "spanish", "german", "arabic", "italian", "chinese", "japanese"
]

GENERIC_WORDS = {"some", "about", "me", "a", "an", "the", "on", "in", "to", "for", "with", "of", "at", "by", "from", "and", "or", "is", "are", "was", "were", "it", "that", "this", "as", "be", "do", "does", "did"}

# Simple intent keywords
QUIZ_KEYWORDS = ["quiz", "test me", "questions", "practice questions"]
EXPLAIN_KEYWORDS = ["explain", "explanation", "clarify", "understand"]
SUMMARY_KEYWORDS = ["summarize", "summary", "short version"]
HELP_KEYWORDS = ["help", "how to study", "tips", "advice", "improve", "technique"]

MAX_HISTORY = 8  # Number of messages to keep in context (not used in single-turn mode)

PLAIN_SYSTEM_PROMPT = (
    "You are a helpful AI study assistant. Only answer study-related questions. "
    "Always reply in plain text. Never use any markdown, stars, hashtags, bold, or special formatting. "
    "If you need to show a list, use numbers or dashes. If you need to show code, write it as plain text. "
    "Be clear, direct, and easy to understand."
)

# Function to clean up markdown, stars, hashtags, and bold from AI response
def clean_ai_response(text):
    # Remove markdown bold/italic/code, stars, hashtags
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*([^*]+)\*', r'\1', text)        # *italic*
    text = re.sub(r'`([^`]+)`', r'\1', text)           # `code`
    text = re.sub(r'#+\s*', '', text)                  # # headers
    text = re.sub(r'\*', '', text)                     # stray stars
    text = re.sub(r'\s*\n\s*', '\n', text)          # clean up newlines
    return text.strip()

# Improved subject extraction

def extract_subject(text):
    text_lower = text.lower()
    # 1. Look for known subjects in the message
    for subject in COMMON_SUBJECTS:
        if subject in text_lower:
            return subject.capitalize()
    # 2. Extract nouns/phrases, ignore generic words
    words = re.findall(r'\b\w+\b', text_lower)
    candidates = [w for w in words if w not in GENERIC_WORDS]
    # 3. Return the last candidate if no known subject found
    if candidates:
        return candidates[-1].capitalize()
    return None

def detect_intent(text):
    text = text.lower()
    if any(word in text for word in QUIZ_KEYWORDS):
        return "quiz"
    if any(word in text for word in EXPLAIN_KEYWORDS):
        return "explain"
    if any(word in text for word in SUMMARY_KEYWORDS):
        return "summary"
    if any(word in text for word in HELP_KEYWORDS):
        return "help"
    return None

# Helper for fade-in animation
def fade_in(widget, steps=10, delay=15):
    try:
        widget.update()
        widget.attributes('-alpha', 0)
        for i in range(steps + 1):
            alpha = i / steps
            widget.attributes('-alpha', alpha)
            widget.update()
            widget.after(delay)
        widget.attributes('-alpha', 1)
    except Exception:
        pass  # Not all widgets support alpha

# Helper for button hover effect
class HoverButton(ctk.CTkButton):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.default_fg = self.cget("fg_color")
        self.hover_fg = kwargs.get("hover_color", "#3B82F6")
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
    def on_enter(self, event):
        self.configure(fg_color=self.hover_fg)
    def on_leave(self, event):
        self.configure(fg_color=self.default_fg)

class YourAssistantApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Your Assistant")
        self.geometry("800x600")
        self.resizable(False, False)
        self.configure(fg_color="#181F2A")

        # Track all unique subjects for quizzes and to-do lists
        self.subjects_set = set()
        self.quiz_data = None
        self.quiz_index = 0
        self.quiz_score = 0
        self.current_quiz_subject = None
        self.todo_lists = {}  # {subject: [ {"task": str, "done": bool} ]}
        self.current_todo_subject = None
        self.todo_task_vars = []

        # --- Preserve chat history ---
        self.chat_history_content = []  # List of (sender, message) tuples

        # Navigation
        self.nav_frame = ctk.CTkFrame(self, width=200)
        self.nav_frame.pack(side="left", fill="y")
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(side="right", fill="both", expand=True)

        self.sections = {
            "Chatbot": self.show_chatbot,
            "To-Do List": self.show_todo,
            "AI Quiz": self.show_quiz
        }
        for i, (name, func) in enumerate(self.sections.items()):
            btn = HoverButton(self.nav_frame, text=name, command=func, fg_color="#2563EB", hover_color="#1E40AF", corner_radius=12, font=("Arial", 16))
            btn.pack(pady=20, padx=10, fill="x")

        self.current_section = None
        self.show_chatbot()

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def fade_in_section(self):
        try:
            self.content_frame.update()
            self.content_frame.attributes('-alpha', 0)
            for i in range(11):
                alpha = i / 10
                self.content_frame.attributes('-alpha', alpha)
                self.content_frame.update()
                self.content_frame.after(10)
            self.content_frame.attributes('-alpha', 1)
        except Exception:
            pass

    # --- Chatbot Section ---
    def show_chatbot(self):
        self.clear_content()
        self.fade_in_section()
        label = ctk.CTkLabel(self.content_frame, text="Study-Only Chatbot", font=("Arial", 24, "bold"), text_color="#60A5FA")
        label.pack(pady=10)

        # Chat history display
        self.chat_history = ctk.CTkTextbox(self.content_frame, width=540, height=350, state="disabled")
        self.chat_history.pack(pady=10)

        # Restore chat history
        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", tk.END)
        if not self.chat_history_content:
            self.append_chat("Assistant", "Hi! I'm your study assistant. Ask me anything about your studies, and I'll help you with explanations, summaries, quizzes, or study tips!")
        else:
            for sender, message in self.chat_history_content:
                self.chat_history.insert(tk.END, f"{sender}: {message}\n")
        self.chat_history.configure(state="disabled")
        self.chat_history.see(tk.END)

        # User input
        self.user_input = ctk.CTkEntry(self.content_frame, width=400, font=("Arial", 14))
        self.user_input.pack(side="left", padx=(40, 10), pady=10)
        self.user_input.bind("<Return>", lambda event: self.send_message())

        # Send button
        send_btn = ctk.CTkButton(self.content_frame, text="Send", command=self.send_message)
        send_btn.pack(side="left", pady=10)

        # For threading
        self.content_frame.pack_propagate(False)

    def send_message(self):
        user_msg = self.user_input.get().strip()
        if not user_msg:
            return
        self.user_input.delete(0, tk.END)
        self.append_chat("You", user_msg)
        # Improved subject extraction
        subject = extract_subject(user_msg)
        if subject:
            self.subjects_set.add(subject)
        # Detect intent and proactively help
        intent = detect_intent(user_msg)
        if intent == "quiz":
            self.append_chat("Assistant", "Sure! What topic or subject would you like to be quizzed on?")
        elif intent == "explain":
            self.append_chat("Assistant", "I'd be happy to explain! What specific concept or topic do you need help with?")
        elif intent == "summary":
            self.append_chat("Assistant", "Of course! Please tell me what you want summarized.")
        elif intent == "help":
            self.append_chat("Assistant", "Here are some study tips: Try the Pomodoro technique, use active recall, and space out your revision. Would you like more details or a study plan?")
        # Only send the latest user message (single-turn mode)
        threading.Thread(target=self.get_ai_response, args=(user_msg,), daemon=True).start()

    def append_chat(self, sender, message):
        # Save to persistent chat history
        self.chat_history_content.append((sender, message))
        self.chat_history.configure(state="normal")
        self.chat_history.insert(tk.END, f"{sender}: {message}\n")
        self.chat_history.configure(state="disabled")
        self.chat_history.see(tk.END)

    def get_ai_response(self, user_msg):
        try:
            print("[DEBUG] Sending to DeepSeek API (single-turn):", user_msg)
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://your-assistant.local",  # Optional
                    "X-Title": "Your Assistant",  # Optional
                },
                extra_body={},
                model="deepseek/deepseek-r1:free",
                messages=[
                    {"role": "system", "content": PLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ]
            )
            print("[DEBUG] DeepSeek API response:", completion)
            ai_msg = completion.choices[0].message.content
            ai_msg = clean_ai_response(ai_msg)
        except Exception as e:
            print("[ERROR] DeepSeek API call failed:", e)
            ai_msg = f"[Error contacting AI: {e}]"
        self.append_chat("Assistant", ai_msg)

    # --- Quiz Section ---
    def show_quiz(self):
        self.clear_content()
        self.fade_in_section()
        label = ctk.CTkLabel(self.content_frame, text="AI Quiz Generator", font=("Arial", 24, "bold"), text_color="#F472B6")
        label.pack(pady=10)
        if self.subjects_set:
            for subject in sorted(self.subjects_set):
                quiz_btn = ctk.CTkButton(self.content_frame, text=f"{subject} Quiz", command=lambda s=subject: self.start_quiz(s))
                quiz_btn.pack(pady=8)
        else:
            info = ctk.CTkLabel(self.content_frame, text="Ask the chatbot to teach you a subject first!", font=("Arial", 16))
            info.pack(pady=40)
        # Quiz area
        self.quiz_area = ctk.CTkFrame(self.content_frame)
        self.quiz_area.pack(pady=10, fill="both", expand=True)

    def start_quiz(self, subject):
        self.current_quiz_subject = subject
        self.quiz_data = None
        self.quiz_index = 0
        self.quiz_score = 0
        self.clear_quiz_area()
        loading = ctk.CTkLabel(self.quiz_area, text=f"Generating {subject} quiz... Please wait.", font=("Arial", 16))
        loading.pack(pady=20)
        threading.Thread(target=self.fetch_quiz_questions, args=(subject,), daemon=True).start()

    def clear_quiz_area(self):
        for widget in self.quiz_area.winfo_children():
            widget.destroy()

    def fetch_quiz_questions(self, subject):
        prompt = (
            f"Create a 4-question multiple choice quiz about {subject}. "
            "For each question, provide 4 answer choices (A, B, C, D) and indicate the correct answer. "
            "Format the quiz as plain text, like this: "
            "Question: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: ...\nRepeat for all 4 questions."
        )
        try:
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://your-assistant.local",
                    "X-Title": "Your Assistant",
                },
                extra_body={},
                model="deepseek/deepseek-r1:free",
                messages=[
                    {"role": "system", "content": PLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            quiz_text = completion.choices[0].message.content
            print(f"[DEBUG] Quiz raw text for {subject}:\n", quiz_text)
            self.quiz_data = self.parse_quiz(quiz_text)
        except Exception as e:
            self.quiz_data = None
            self.quiz_area.after(0, self.show_quiz_error, f"[Error generating quiz: {e}]")
            return
        self.quiz_area.after(0, self.show_next_question)

    def parse_quiz(self, text):
        # Parse the quiz text into a list of dicts: [{question, choices, answer}]
        questions = []
        q_blocks = re.split(r'Question:', text)[1:]  # Skip any intro text
        for block in q_blocks:
            lines = block.strip().splitlines()
            if len(lines) < 5:
                continue
            question = lines[0].strip()
            choices = {}
            for line in lines[1:5]:
                if ")" in line:
                    key, val = line.split(")", 1)
                    choices[key.strip()] = val.strip()
            answer = None
            for line in lines[5:]:
                if line.lower().startswith("answer:"):
                    answer = line.split(":", 1)[-1].strip().upper()
                    break
            if question and choices and answer:
                questions.append({"question": question, "choices": choices, "answer": answer})
        return questions

    def show_next_question(self):
        self.clear_quiz_area()
        if not self.quiz_data or self.quiz_index >= len(self.quiz_data):
            result = ctk.CTkLabel(self.quiz_area, text=f"Quiz complete! Your score: {self.quiz_score}/{len(self.quiz_data) if self.quiz_data else 4}", font=("Arial", 18))
            result.pack(pady=30)
            return
        q = self.quiz_data[self.quiz_index]
        q_label = ctk.CTkLabel(self.quiz_area, text=f"Q{self.quiz_index+1}: {q['question']}", font=("Arial", 16), wraplength=500, justify="left")
        q_label.pack(pady=10)
        self.selected_answer = tk.StringVar()
        for key in ["A", "B", "C", "D"]:
            if key in q["choices"]:
                rb = ctk.CTkRadioButton(self.quiz_area, text=f"{key}) {q['choices'][key]}", variable=self.selected_answer, value=key)
                rb.pack(anchor="w", padx=30, pady=2)
        submit_btn = ctk.CTkButton(self.quiz_area, text="Submit", command=self.check_answer)
        submit_btn.pack(pady=10)
        self.feedback_label = ctk.CTkLabel(self.quiz_area, text="", font=("Arial", 14))
        self.feedback_label.pack(pady=5)

    def check_answer(self):
        q = self.quiz_data[self.quiz_index]
        selected = self.selected_answer.get()
        if not selected:
            self.feedback_label.configure(text="Please select an answer.")
            return
        if selected == q["answer"]:
            self.feedback_label.configure(text="Correct!", text_color="green")
            self.quiz_score += 1
        else:
            correct_text = q["choices"].get(q["answer"], "")
            self.feedback_label.configure(text=f"Wrong. Correct answer: {q['answer']}) {correct_text}", text_color="red")
        self.quiz_index += 1
        self.quiz_area.after(1200, self.show_next_question)

    def show_quiz_error(self, msg):
        self.clear_quiz_area()
        err = ctk.CTkLabel(self.quiz_area, text=msg, font=("Arial", 14), text_color="red")
        err.pack(pady=20)

    # --- To-Do List Section ---
    def show_todo(self):
        self.clear_content()
        self.fade_in_section()
        label = ctk.CTkLabel(self.content_frame, text="AI To-Do List", font=("Arial", 24, "bold"), text_color="#34D399")
        label.pack(pady=10)
        if self.subjects_set:
            for subject in sorted(self.subjects_set):
                todo_btn = ctk.CTkButton(self.content_frame, text=f"{subject} To-Do List", command=lambda s=subject: self.show_todo_for_subject(s))
                todo_btn.pack(pady=8)
        else:
            info = ctk.CTkLabel(self.content_frame, text="Ask the chatbot to teach you a subject first!", font=("Arial", 16))
            info.pack(pady=40)
        # To-Do area
        self.todo_area = ctk.CTkFrame(self.content_frame)
        self.todo_area.pack(pady=10, fill="both", expand=True)

    def show_todo_for_subject(self, subject):
        self.current_todo_subject = subject
        self.clear_todo_area()
        self.todo_area.update()
        # Fade-in animation for new tasks area
        try:
            self.todo_area.attributes('-alpha', 0)
            for i in range(11):
                alpha = i / 10
                self.todo_area.attributes('-alpha', alpha)
                self.todo_area.update()
                self.todo_area.after(10)
            self.todo_area.attributes('-alpha', 1)
        except Exception:
            pass
        title = ctk.CTkLabel(self.todo_area, text=f"{subject} To-Do List", font=("Arial", 18, "bold"), text_color="#FBBF24")
        title.pack(pady=5)
        # If no tasks, generate with AI
        if not self.todo_lists.get(subject):
            loading = ctk.CTkLabel(self.todo_area, text="Generating to-do list... Please wait.", font=("Arial", 16))
            loading.pack(pady=20)
            threading.Thread(target=self.fetch_todo_tasks, args=(subject,), daemon=True).start()
            return
        # Entry to add new task
        entry_frame = ctk.CTkFrame(self.todo_area)
        entry_frame.pack(pady=5)
        new_task_var = tk.StringVar()
        entry = ctk.CTkEntry(entry_frame, width=300, textvariable=new_task_var)
        entry.pack(side="left", padx=5)
        add_btn = ctk.CTkButton(entry_frame, text="Add Task", command=lambda: self.add_todo_task(subject, new_task_var))
        add_btn.pack(side="left", padx=5)
        # Scrollable frame for tasks
        canvas = tk.Canvas(self.todo_area, borderwidth=0, height=320)
        scrollbar = ctk.CTkScrollbar(self.todo_area, orientation="vertical", command=canvas.yview)
        scroll_frame = ctk.CTkFrame(canvas)
        scroll_frame_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        scroll_frame.bind("<Configure>", on_frame_configure)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        # List tasks in scrollable frame
        self.todo_task_vars = []  # For checkboxes
        for idx, item in enumerate(self.todo_lists[subject]):
            var = tk.BooleanVar(value=item["done"])
            cb = ctk.CTkCheckBox(scroll_frame, text=item["task"], variable=var, command=lambda i=idx, v=var: self.toggle_todo_task(subject, i, v))
            cb.pack(anchor="w", padx=20, pady=2)
            self.todo_task_vars.append(var)
            del_btn = ctk.CTkButton(scroll_frame, text="Remove", width=60, command=lambda i=idx: self.remove_todo_task(subject, i))
            del_btn.pack(anchor="w", padx=40, pady=1)

    def clear_todo_area(self):
        for widget in self.todo_area.winfo_children():
            widget.destroy()

    def fetch_todo_tasks(self, subject):
        prompt = (
            f"Give me a helpful, actionable to-do list for a student studying {subject}. "
            "List 5-8 specific tasks or steps. Reply in plain text, one task per line, no numbering or bullets."
        )
        try:
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://your-assistant.local",
                    "X-Title": "Your Assistant",
                },
                extra_body={},
                model="deepseek/deepseek-r1:free",
                messages=[
                    {"role": "system", "content": PLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            todo_text = completion.choices[0].message.content
            print(f"[DEBUG] To-Do AI response for {subject}:\n", todo_text)
            tasks = [line.strip() for line in todo_text.splitlines() if line.strip()]
            self.todo_lists[subject] = [{"task": t, "done": False} for t in tasks]
        except Exception as e:
            self.todo_lists[subject] = []
            self.todo_area.after(0, self.show_todo_error, f"[Error generating to-do list: {e}]")
            return
        self.todo_area.after(0, lambda: self.show_todo_for_subject(subject))

    def show_todo_error(self, msg):
        self.clear_todo_area()
        err = ctk.CTkLabel(self.todo_area, text=msg, font=("Arial", 14), text_color="red")
        err.pack(pady=20)

    def add_todo_task(self, subject, new_task_var):
        task = new_task_var.get().strip()
        if not task:
            return
        self.todo_lists.setdefault(subject, []).append({"task": task, "done": False})
        new_task_var.set("")
        self.show_todo_for_subject(subject)

    def toggle_todo_task(self, subject, idx, var):
        self.todo_lists[subject][idx]["done"] = var.get()

    def remove_todo_task(self, subject, idx):
        del self.todo_lists[subject][idx]
        self.show_todo_for_subject(subject)

if __name__ == "__main__":
    app = YourAssistantApp()
    app.mainloop() 