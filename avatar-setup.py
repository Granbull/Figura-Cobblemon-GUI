import json
import os
import re
import shutil
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

def global_fix_math_expr(expr):
    if not isinstance(expr, str): return expr

    stripped = expr.strip()
    try:
        # If the expression is just a simple number (e.g., "-5", "3.14"), 
        # return it as-is to prevent it from being compiled as a math operation
        float(stripped)
        return stripped
    except ValueError:
        pass

    # Strip non-ASCII characters
    expr = re.sub(r'[^\x00-\x7F]+', '', expr)

    # Clean up newlines and backslashes
    expr = expr.replace('\n', ' ').replace('\r', ' ')
    expr = expr.replace('\\', '')
    
    # Fix stray equals signs (truncate them and anything after, as they invalidate math)
    expr = re.sub(r'(?<![=<>!~])=(?!=).*', '', expr)

    # Remove unary plus (invalid in Lua)
    expr = re.sub(r'^\s*\+', '', expr)
    expr = re.sub(r'([+\-*/<>=(,])\s*\+', r'\1', expr)
    
    # Fix unary minus at the start of the expression to avoid block parsing errors
    expr = re.sub(r'^\s*-(?=[a-zA-Z(])', '0-', expr)

    # Fix missing operators causing "unexpected symbol 287 (ğ)" (Token ID 287 is <number>, kcin is a god)
    # E.g. `q.r.pitch(0)30` -> `q.r.pitch(0) + 30`
    expr = re.sub(r'\)\s*(?=[0-9]|q\.|math\.|v\.|query\.)', ') + ', expr)
    expr = re.sub(r'([0-9])\s*(?=q\.|math\.|v\.|query\.)', r'\1 + ', expr)
    # Fix implicit multiplication like `30(-1)` -> `30 * (-1)`
    expr = re.sub(r'([0-9])\s*(?=\()', r'\1 * ', expr)
    
    # Fix hanging operators before closing parenthesis (e.g. `55+)` -> `55)`)
    expr = re.sub(r'([+\-*/])\s*\)', ')', expr)

    # Extract statements from Molang conditionals directly (e.g. q.is_gliding ? { q.sound('foo'); } -> q.sound('foo'))
    expr = re.sub(r'.+?\s*\?\s*{\s*(.+?);\s*}', r'\1', expr)

    # Convert q.sound to the avatar's KeySound function
    expr = expr.replace("q.sound", "KeySound")

    # Fix `time` -> `q.anim_time` (Prevents Lua from calling the global time() function)
    expr = re.sub(r'(?<![a-zA-Z0-9_.])time\b', 'q.anim_time', expr)
    
    # Fix Molang logical operators -> Lua logical operators
    expr = expr.replace('&&', ' and ')
    expr = expr.replace('||', ' or ')
    expr = expr.replace('!=', ' ~= ')
    
    # Fix numeric booleans like `!0` (true -> 1) and `!1` (false -> 0) BEFORE general `!` replacement
    expr = re.sub(r'!\s*0\b', '1', expr)
    expr = re.sub(r'!\s*1\b', '0', expr)
    expr = re.sub(r'!(?!=)', ' not ', expr)
    
    # Fix malformed numbers with double decimals like `0.1.5` -> `0.15`
    expr = re.sub(r'([0-9]+\.[0-9]+)\.([0-9]+)', r'\1\2', expr)
    
    # UGLY HARDCODING BLOCK!!!
    # I hate that I'm hardcoding this. Fixes SPECIFICALLY Vulpix's ground_run tail_left2_3 keyframe.
    # Math.sin(q.anim_time*90*8-30 0)*15) <--- WHAT IS THE SPACE DOING THERE????
    expr = re.sub(r'\b30\s+0\b', '30.0', expr)
    # Fixes Bronzong's sleep arm_right3 keyframe.
    # math.clampq.r.input_right(18) + (q.r.velocity_right(8),-1,0)*-20 <--- ??????????
    expr = re.sub(r'math\.clampq\.r\.input_right\(18\)\s*\+\s*\(q\.r\.velocity_right\(8\),\s*-1,\s*0\)', 'math.clamp(q.r.input_right(18) + q.r.velocity_right(8), -1, 0)', expr)

    # Fix ternary operators `? :` -> `and` `or` (Prevents Lua syntax errors)
    if '?' in expr and ':' in expr:
        expr = re.sub(r'\s*\?\s*', ' and ', expr)
        expr = re.sub(r'\s*:\s*', ' or ', expr)
        
    # Fix missing parentheses on function calls (e.g. q.r.yaw_change -> q.r.yaw_change())
    expr = re.sub(r'(q\.r\.[a-zA-Z0-9_]+)(?![a-zA-Z0-9_.]|\()', r'\g<1>()', expr)
    expr = re.sub(r'\b(math\.random)(?![a-zA-Z0-9_]|\()', r'\g<1>()', expr, flags=re.IGNORECASE)
    
    # Fix broken clamps with empty arguments like `,-,`
    expr = re.sub(r',\s*-\s*,', ', 0,', expr)
    expr = re.sub(r',\s*\+\s*,', ', 0,', expr)
    
    # Fix missing arguments at the end of functions like `,-,)` or `,)` -> `, 0)`
    expr = re.sub(r',\s*[-+]?\s*\)', ', 0)', expr)
    
    # Fix math typos and case sensitivity (e.g., Math.sin -> math.sin)
    # Note: sin and cos must map to Math.sin and Math.cos for degree conversions
    expr = re.sub(r'\b(?:math|ath|mth|mah|mat)\.(sin|cos|clamp|abs|pi|random|round|ceil|floor|min|max|pow|sqrt|exp|mod|fmod)\b', lambda m: f"Math.{m.group(1).lower()}" if m.group(1).lower() in ['sin', 'cos'] else f"math.{m.group(1).lower()}", expr, flags=re.IGNORECASE)
    
    # Fix missing parens for math functions
    expr = re.sub(r'\b(math\.(?:sin|cos|clamp|abs|pi|random|round|ceil|floor|min|max|pow|sqrt|exp|mod|fmod))(?=q\.|math\.|v\.|query\.)', r'\1(', expr, flags=re.IGNORECASE)

    # Fix uppercase Molang variables (e.g., Q.anim_time -> q.anim_time)
    expr = re.sub(r'\bq\.', 'q.', expr, flags=re.IGNORECASE)
    expr = re.sub(r'\bquery\.', 'query.', expr, flags=re.IGNORECASE)
    expr = re.sub(r'\bv\.', 'v.', expr, flags=re.IGNORECASE)
    expr = re.sub(r'\bvariable\.', 'variable.', expr, flags=re.IGNORECASE)

    # Balance parentheses (fixes extra/dangling parentheses)
    open_count = 0
    res = []
    for char in expr:
        if char == '(':
            open_count += 1
            res.append(char)
        elif char == ')':
            if open_count > 0:
                open_count -= 1
                res.append(char)
        else:
            res.append(char)
    expr = ''.join(res)
    if open_count > 0:
        expr += ')' * open_count

    # Fix hanging operators at the end of expressions
    expr = re.sub(r'([+\-*/<>=(,]\s*)+$', '', expr)
    
    return expr


def global_search_outliner(uuid_to_name, nodes, current_path, search_target):
    for node in nodes:
        # Ignore any cubes and meshes (strings), take groups (dicts)
        if isinstance(node, dict):
            name = node.get("name", "")
            if not name and "uuid" in node:
                name = uuid_to_name.get(node["uuid"], "")
                
            name = str(name)
            new_path = current_path + [name]
            if name.strip().lower() == search_target.strip().lower():
                return new_path
            
            children = node.get("children", [])
            if isinstance(children, list) and children:
                result = global_search_outliner(uuid_to_name, children, new_path, search_target)
                if result:
                    return result
    return None

class AvatarBuilderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cobblemon Avatar Setup")
        self.root.config(padx=20, pady=10)
        self.root.minsize(400, 380)
        self.root.minsize(400, 380)
        
        # cute little icon
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
            self.icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        else:
            self.base_path = os.path.dirname(os.path.realpath(__file__))
            self.icon_path = os.path.join(self.base_path, "icon.ico")
            
        # linux/macos users hate cute little icons
        if sys.platform == 'win32' and os.path.exists(self.icon_path):
            self.root.iconbitmap(default=self.icon_path)
            
        # Default values for advanced settings
        self.scale_var = tk.StringVar(value="1")
        self.camheight_var = tk.StringVar(value="1")
        self.nameplatepivot_var = tk.StringVar(value="1")
        self.pdollscale_var = tk.StringVar(value="1")
        self.speedscale_var = tk.BooleanVar(value=False)
        self.movespeed_var = tk.StringVar(value="0.35")
        self.customcry_var = tk.BooleanVar(value=False)
        self.cryfile_var = tk.StringVar(value="")
        self.crosshair_var = tk.BooleanVar(value=True)
        self.extra_anims_var = tk.BooleanVar(value=False)
        self.status_timer = None
        
        # Checking if there's a valid avatar
        def is_valid_avatar_dir(path):
            return os.path.exists(os.path.join(path, "avatar.json")) and os.path.exists(os.path.join(path, "config.lua"))

        if not is_valid_avatar_dir(self.base_path):
            messagebox.showinfo("Select Folder", "No valid avatar found in the current folder.\n\nPlease select your avatar folder.")
            selected_dir = filedialog.askdirectory(title="Select Avatar Folder")
            if not selected_dir:
                self.root.destroy()
                return
            self.base_path = selected_dir
            if not is_valid_avatar_dir(self.base_path):
                messagebox.showerror("Error", "The selected folder does not contain an avatar.json and config.lua. Closing.")
                self.root.destroy()
                return
            
        self.setup_ui()
        self.load_posers()
        self.refresh_models()
        
    def setup_ui(self):
        main_input_frame = tk.Frame(self.root)
        main_input_frame.pack(pady=(15, 5))
        
        # Model Selection
        tk.Label(main_input_frame, text="Select .bbmodel:").grid(row=0, column=0, columnspan=2, pady=(0,2))
        
        self.model_var = tk.StringVar()
        self.model_cb = ttk.Combobox(main_input_frame, textvariable=self.model_var, state="readonly", width=30)
        self.model_cb.grid(row=1, column=0, sticky="w", padx=(0, 5))
        self.model_cb.bind("<<ComboboxSelected>>", self.on_model_select)
        tk.Button(main_input_frame, text="Refresh", command=self.refresh_models, width=8).grid(row=1, column=1)
        
        # Poser Selection
        tk.Label(main_input_frame, text="Select Poser:").grid(row=2, column=0, columnspan=2, pady=(10,2))
        
        self.poser_var = tk.StringVar()
        self.poser_cb = ttk.Combobox(main_input_frame, textvariable=self.poser_var, state="readonly", width=30)
        self.poser_cb.grid(row=3, column=0, sticky="w", padx=(0, 5))
        tk.Button(main_input_frame, text="Auto", command=self.auto_detect_poser, width=8).grid(row=3, column=1)
        
        # Head Path
        tk.Label(main_input_frame, text="Head Group Path:").grid(row=4, column=0, columnspan=2, pady=(10,2))
        
        head_inner_frame = tk.Frame(main_input_frame)
        head_inner_frame.grid(row=5, column=0, sticky="w", padx=(0, 5))
        
        self.head_prefix_var = tk.StringVar()
        tk.Label(head_inner_frame, textvariable=self.head_prefix_var, fg="gray").pack(side=tk.LEFT)
        self.head_var = tk.StringVar()
        tk.Entry(head_inner_frame, textvariable=self.head_var, width=18).pack(side=tk.LEFT)
        
        tk.Button(main_input_frame, text="Auto", command=self.auto_find_head_path, width=8).grid(row=5, column=1)
        
        # Advanced Settings Button
        self.adv_toggle_btn = tk.Button(self.root, text="Advanced Settings ▼", command=self.toggle_advanced_settings)
        self.adv_toggle_btn.pack(pady=(15, 5))
        
        self.adv_frame = tk.Frame(self.root)

        # Pokémon Scale
        tk.Label(self.adv_frame, text="Pokémon Scale:").grid(row=0, column=0, sticky="e", pady=2)
        tk.Entry(self.adv_frame, textvariable=self.scale_var, width=10).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Camera Height
        tk.Label(self.adv_frame, text="Camera Height:").grid(row=1, column=0, sticky="e", pady=2)
        tk.Entry(self.adv_frame, textvariable=self.camheight_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        # Nameplate Pivot
        tk.Label(self.adv_frame, text="Nameplate Pivot:").grid(row=2, column=0, sticky="e", pady=2)
        tk.Entry(self.adv_frame, textvariable=self.nameplatepivot_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=2)

        # Paperdoll Scale
        tk.Label(self.adv_frame, text="Paperdoll Scale:").grid(row=3, column=0, sticky="e", pady=2)
        tk.Entry(self.adv_frame, textvariable=self.pdollscale_var, width=10).grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Speed Scale
        tk.Label(self.adv_frame, text="Speed Scale:").grid(row=4, column=0, sticky="e", pady=2)
        speed_frame = tk.Frame(self.adv_frame)
        speed_frame.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        tk.Checkbutton(speed_frame, variable=self.speedscale_var, command=lambda: toggle_speed()).pack(side=tk.LEFT)
        speed_opt = tk.Frame(speed_frame)
        tk.Label(speed_opt, text="Speed:").pack(side=tk.LEFT, padx=(5,2))
        tk.Entry(speed_opt, textvariable=self.movespeed_var, width=6).pack(side=tk.LEFT)
        
        def toggle_speed():
            if self.speedscale_var.get():
                speed_opt.pack(side=tk.LEFT)
            else:
                speed_opt.pack_forget()
        self.toggle_speed_fn = toggle_speed
        toggle_speed()

        # Custom Cry
        tk.Label(self.adv_frame, text="Custom Cry:").grid(row=5, column=0, sticky="e", pady=2)
        cry_frame = tk.Frame(self.adv_frame)
        cry_frame.grid(row=5, column=1, sticky="w", padx=5, pady=2)
        tk.Checkbutton(cry_frame, variable=self.customcry_var, command=lambda: toggle_cry()).pack(side=tk.LEFT)
        cry_opt = tk.Frame(cry_frame)
        cry_btn = tk.Button(cry_opt, text="Select .ogg", command=lambda: select_cry())
        cry_btn.pack(side=tk.LEFT, padx=(5,2))

        def select_cry():
            filepath = filedialog.askopenfilename(parent=self.root, filetypes=[("OGG Audio Files", "*.ogg")])
            if filepath:
                self.cryfile_var.set(filepath)
                cry_btn.config(text="OK!")
        
        def toggle_cry():
            if self.customcry_var.get():
                cry_opt.pack(side=tk.LEFT)
                if self.cryfile_var.get():
                    cry_btn.config(text="OK!")
                else:
                    cry_btn.config(text="Select .ogg")
            else:
                cry_opt.pack_forget()
        self.toggle_cry_fn = toggle_cry
        self.cry_btn = cry_btn
        toggle_cry()

        # Crosshair Adjust
        tk.Label(self.adv_frame, text="Crosshair Adjust:").grid(row=6, column=0, sticky="e", pady=2)
        tk.Checkbutton(self.adv_frame, variable=self.crosshair_var).grid(row=6, column=1, sticky="w", padx=5, pady=2)

        # Extra Animations
        tk.Label(self.adv_frame, text="Extra Animations:").grid(row=7, column=0, sticky="e", pady=2)
        tk.Checkbutton(self.adv_frame, variable=self.extra_anims_var).grid(row=7, column=1, sticky="w", padx=5, pady=2)

        self.adv_frame.grid_columnconfigure(0, minsize=150)
        self.adv_frame.grid_columnconfigure(1, minsize=190)
        self.adv_expanded = False
        
        # Run Button
        self.run_btn = tk.Button(self.root, text="Run Setup", command=self.run_setup, width=15)
        self.run_btn.pack(pady=(20, 5))
        
        # Status Label
        self.status_label = tk.Label(self.root, text="", fg="green", wraplength=300)
        self.status_label.pack(pady=(0, 5))

        # Footer
        footer_text = "Based on the work of kcin2001\nMade with ♥ by Granbull"
        tk.Label(self.root, text=footer_text, fg="grey", font=("Segoe UI", 8)).pack(side=tk.BOTTOM, pady=(0, 5))

    def toggle_advanced_settings(self):
        if self.adv_expanded:
            self.adv_frame.pack_forget()
            self.adv_toggle_btn.config(text="Advanced Settings ▼")
            
            self.root.minsize(400, 380)
            self.adv_expanded = False
        else:
            self.adv_frame.pack(before=self.run_btn, pady=5)
            self.adv_toggle_btn.config(text="Advanced Settings ▲")
            
            self.root.minsize(400, 580)
            self.adv_expanded = True
        
    def show_status(self, text, color="green"):
        self.status_label.config(text=text, fg=color)
        if self.status_timer:
            self.root.after_cancel(self.status_timer)
        if text:
            timeout = 5000 if color == "red" else 3000
            self.status_timer = self.root.after(timeout, lambda: self.status_label.config(text=""))

    def refresh_models(self):
        models = [f for f in os.listdir(self.base_path) if f.endswith(".bbmodel")]
        self.model_cb['values'] = models
        if models:
            self.model_cb.current(0)
            self.on_model_select()
        else:
            self.model_cb.set('')
            self.on_model_select()
            self.show_status("Place a .bbmodel file in this folder and click Refresh.", "red")

    def on_model_select(self, event=None):
        model_file = self.model_var.get()
        if model_file:
            modelname = model_file.rsplit(".bbmodel", 1)[0]
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', modelname):
                self.head_prefix_var.set(f"models.{modelname}.")
            else:
                escaped_modelname = modelname.replace("'", "\\'")
                self.head_prefix_var.set(f"models['{escaped_modelname}'].")
        else:
            self.head_prefix_var.set("models.")
        self.load_avatar_config()

    def load_avatar_config(self):
        avatar_path = os.path.join(self.base_path, "avatar.json")
        config_path = os.path.join(self.base_path, "config.lua")

        # 1. Read avatar.json for Poser and Extra Animations
        if os.path.exists(avatar_path):
            try:
                with open(avatar_path, "r", encoding="utf-8-sig") as f:
                    meta = json.load(f)
                
                auto_scripts = []
                for k, v in meta.items():
                    if k.lower() in ("autoscripts", "auto_scripts") and isinstance(v, list):
                        auto_scripts = [s.replace("\\", "/").strip() for s in v if isinstance(s, str)]
                        break

                self.extra_anims_var.set(any(s.lower() in ("poser/extras", "poser/extras.lua") for s in auto_scripts))
                
                for script in reversed(auto_scripts):
                    if not script or "extras" in script.lower() or "priority" in script.lower():
                        continue
                    filename = re.split(r'[/\\]', script)[-1]
                    raw = re.sub(r'[^a-z0-9]', '', re.sub(r'\.lua$', '', filename, flags=re.I).lower())
                    if not raw:
                        continue
                    
                    matched = False
                    for idx, val in enumerate(self.poser_cb['values']):
                        norm_val = re.sub(r'[^a-z0-9]', '', val.lower())
                        norm_map = re.sub(r'[^a-z0-9]', '', self.poser_mapping.get(val, "").lower())
                        if raw in (norm_val, norm_map):
                            self.poser_var.set(val)
                            self.poser_cb.set(val)
                            self.poser_cb.current(idx)
                            matched = True
                            break
                    if matched:
                        break
            except Exception:
                pass

        # 2. Read config.lua for Head Path and Advanced Options
        if not os.path.exists(config_path):
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()
        except Exception:
            return

        # Check if head path is uninitialized template placeholder
        head_match = re.search(r'\["head"\]\s*=\s*([^,\n\r]+)', config_content)
        if head_match:
            head_val = head_match.group(1).strip()
            if "NAME_HERE" not in head_val and "PATH.TO.HEAD" not in head_val:
                # Extract head group suffix
                prefix = self.head_prefix_var.get()
                prefix_no_dot = prefix[:-1] if prefix.endswith(".") else prefix
                if head_val.startswith(prefix):
                    self.head_var.set(head_val[len(prefix):])
                elif head_val.startswith(prefix_no_dot):
                    self.head_var.set(head_val[len(prefix_no_dot):])
                else:
                    stripped = re.sub(r'^models(?:\[["\'].*?["\']\]|\.[a-zA-Z0-9_-]+)\.?', '', head_val)
                    self.head_var.set(stripped)

        # Parse Advanced Options from config.lua
        def set_str_var(var, pattern):
            m = re.search(pattern, config_content)
            if m:
                var.set(m.group(1).strip())

        def set_bool_var(var, pattern, toggle_fn=None):
            m = re.search(pattern, config_content)
            if m:
                val = m.group(1).strip().lower() == "true"
                var.set(val)
                if toggle_fn:
                    toggle_fn()

        set_str_var(self.scale_var, r'pokescale\s*=\s*([0-9.-]+)')
        set_str_var(self.camheight_var, r'camheight\s*=\s*([0-9.-]+)')
        set_str_var(self.nameplatepivot_var, r'nameplatepivot\s*=\s*([0-9.-]+)')
        set_str_var(self.pdollscale_var, r'pdollscale\s*=\s*([0-9.-]+)')
        set_str_var(self.movespeed_var, r'movespeed\s*=\s*([0-9.-]+)')

        set_bool_var(self.speedscale_var, r'speedscale\s*=\s*(true|false)', lambda: getattr(self, 'toggle_speed_fn', lambda: None)())
        set_bool_var(self.customcry_var, r'customcry\s*=\s*(true|false)', lambda: getattr(self, 'toggle_cry_fn', lambda: None)())
        set_bool_var(self.crosshair_var, r'crosshairAdjust\s*=\s*(true|false)')

        if self.customcry_var.get():
            model_file = self.model_var.get()
            if model_file:
                modelname = model_file.rsplit(".bbmodel", 1)[0]
                expected_cry = os.path.join(self.base_path, f"{modelname}_cry.ogg")
                if os.path.exists(expected_cry):
                    self.cryfile_var.set(expected_cry)
                    if hasattr(self, 'cry_btn'):
                        self.cry_btn.config(text="OK!")

    def auto_detect_poser(self):
        model_file = self.model_var.get()
        if not model_file:
            self.show_status("Error: Please select a .bbmodel file first.", "red")
            return

        model_path = os.path.join(self.base_path, model_file)
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                model_text = f.read()
        except Exception as e:
            self.show_status(f"Error: Failed to read .bbmodel: {str(e)}", "red")
            return
            
        prefix = r'(?:animations?\.[^.\"]+\.)?'
        has_ground = bool(re.search(rf'"name"\s*:\s*"{prefix}(?:ground_idle|ground_walk|ground_run)"', model_text))
        has_water = bool(re.search(rf'"name"\s*:\s*"{prefix}(?:water_idle|water_swim)"', model_text))
        has_surface = bool(re.search(rf'"name"\s*:\s*"{prefix}(?:surfacewater_idle|surfacewater_swim)"', model_text))
        has_air = bool(re.search(rf'"name"\s*:\s*"{prefix}(?:air_idle|air_fly)"', model_text))
        
        # Automatic poser checks, I think the logic is right?
        poser_key = "standard"
        if has_ground and has_air and (has_water or has_surface):
            poser_key = "complete"
        elif has_water and has_surface:
            poser_key = "water"
        elif has_air and not has_water and not has_surface:
            poser_key = "flying"
        elif has_water and not has_surface:
            poser_key = "water_no_surface"
        elif has_surface and not has_water:
            poser_key = "water_only_surface"
            
        target_display_name = next(
            (display for display, raw in self.poser_mapping.items() if raw.lower() == poser_key), 
            None
        )
        
        if target_display_name and target_display_name in self.poser_cb['values']:
            self.poser_var.set(target_display_name)
            self.show_status(f"Poser '{target_display_name}' detected!", "green")
        else:
            standard_key = next((name for name in self.poser_cb['values'] if name.lower() == "standard"), None)
            if standard_key:
                self.poser_var.set(standard_key)
                self.show_status("Defaulted to standard Poser.", "green")

    def auto_find_head_path(self):
        try:
            model_file = self.model_var.get()
            if not model_file:
                self.show_status("Error: Please select a .bbmodel file first.", "red")
                return

            target_input = self.head_var.get().strip()
            original_target = target_input if target_input else "head"

            display_target = original_target
            if display_target.endswith("]"):
                match = re.search(r"\[['\"]([^'\"]+)['\"]\]$", display_target)
                if match:
                    display_target = match.group(1)
            elif "." in display_target:
                display_target = display_target.split(".")[-1]

            model_path = os.path.join(self.base_path, model_file)
            with open(model_path, "r", encoding="utf-8") as f:
                model_text = f.read()
            # Fix NaN and -NaN errors
            model_text = re.sub(r'-?\bNaN\b', "0", model_text)
            model_data = json.loads(model_text)
            
            uuid_to_name = {}
            for group in model_data.get("groups", []):
                if "uuid" in group and "name" in group:
                    uuid_to_name[group["uuid"]] = group["name"]
            
            outliner = model_data.get("outliner", [])
            
            def search_outliner(nodes, current_path, search_target):
                for node in nodes:
                    # Ignore any cubes and meshes (strings), take groups (dicts)
                    if isinstance(node, dict):
                        name = node.get("name", "")
                        if not name and "uuid" in node:
                            name = uuid_to_name.get(node["uuid"], "")
                            
                        name = str(name)
                        new_path = current_path + [name]
                        if name.strip().lower() == search_target.strip().lower():
                            return new_path
                        
                        children = node.get("children", [])
                        if isinstance(children, list) and children:
                            result = search_outliner(children, new_path, search_target)
                            if result:
                                return result
                return None
                
            # 1. Try to find exactly what was typed (important for groups with dots like "arm.L")
            found_path = global_search_outliner(uuid_to_name, outliner, [], original_target)
            
            # 2. If not found, check if it's a previously formatted path and extract the base name
            if not found_path and display_target != original_target:
                found_path = global_search_outliner(uuid_to_name, outliner, [], display_target)
            
            if found_path:
                formatted_suffix = ""
                for p in found_path:
                    # Standard lua dot notation if alphanumeric, otherwise use bracket indexing (models.granbull. vs models["granbull"].)
                    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', p):
                        if formatted_suffix:
                            formatted_suffix += f".{p}"
                        else:
                            formatted_suffix = p
                    else:
                        formatted_suffix += f"['{p}']"
                        
                self.head_var.set(formatted_suffix)
                self.show_status(f"Head group '{found_path[-1]}' detected!", "green")
            else:
                self.show_status(f"Could not find any group named '{display_target}'.", "red")
                
        except Exception as e:
            self.show_status(f"Error: Failed to run Auto Find: {str(e)}", "red")

    def load_posers(self):
        # Unnecessary, but I wanted it to match the order of the original script
        display_names = []
        self.poser_mapping = {}
        poser_dir = os.path.join(self.base_path, "Poser")
        if os.path.exists(poser_dir):
            for file in os.listdir(poser_dir):
                if file.endswith(".lua") and not (file.startswith("priority") or file.startswith("Extras")):
                    raw_name = file.rsplit(".", 1)[0]
                    
                    if raw_name.lower() == "water_no_surface":
                        display_name = "Water (No surface)"
                    elif raw_name.lower() == "water_only_surface":
                        display_name = "Water (Only surface)"
                    else:
                        display_name = raw_name
                        
                    display_names.append(display_name)
                    self.poser_mapping[display_name] = raw_name
        
        preferred_order = [
            "standard",
            "water",
            "water (no surface)",
            "water (only surface)",
            "flying",
            "complete"
        ]
        display_names.sort(key=lambda x: preferred_order.index(x.lower()) if x.lower() in preferred_order else 999)
        
        self.poser_cb['values'] = display_names
        
        standard_key = next((name for name in display_names if name.lower() == "standard"), None)
        if standard_key:
            self.poser_var.set(standard_key)
        elif display_names:
            self.poser_cb.current(0)

    def run_setup(self):
        self.show_status("")
        model_file = self.model_var.get()
        if not model_file:
            self.show_status("Error: Please select a .bbmodel file first.", "red")
            return
            
        poser_display = self.poser_var.get()
        if not poser_display:
            self.show_status("Error: Please select a Poser.", "red")
            return
            
        poser = self.poser_mapping.get(poser_display, poser_display)
        
        modelname = model_file.rsplit(".bbmodel", 1)[0]
        # Clean up model names (e.g. mr_mime -> Mr Mime)
        pokename = modelname.replace("_", " ").title()
        
        head_suffix = self.head_var.get().strip()
        if not head_suffix:
            headpath = '"NONE"'
        else:
            prefix = self.head_prefix_var.get()
            # Clean up double dots if a bracket path follows a dot (e.g. models.granbull.['body'])
            if head_suffix.startswith("[") and prefix.endswith("."):
                prefix = prefix[:-1]
                
            # Fixes groups with protected group names (Fixes Gallade's head)
            headpath = f"{prefix}{head_suffix}"
            for res in ["Head", "Body", "RightArm", "LeftArm", "RightLeg", "LeftLeg", "RightPants", "LeftPants", "Jacket", "Hat"]:
                headpath = headpath.replace(f".{res}", f".{res.lower()}").replace(f"['{res}']", f"['{res.lower()}']")

        scale = self.scale_var.get().strip() or "1"
        camheight = self.camheight_var.get().strip() or "1"
        nameplatepivot = self.nameplatepivot_var.get().strip() or "0"
        pdollscale = self.pdollscale_var.get().strip() or "1"
        speedscale_val = "true" if self.speedscale_var.get() else "false"
        movespeed = self.movespeed_var.get().strip() or "0.35"
        customcry_val = "true" if self.customcry_var.get() else "false"
        crosshair_val = "true" if self.crosshair_var.get() else "false"
            
        try:
            # 1. Update avatar.json
            avatar_path = os.path.join(self.base_path, "avatar.json")
            with open(avatar_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            meta["name"] = pokename.capitalize()
            meta["description"] = f"{pokename.capitalize()} from Cobblemon.   \nUses the GS animblend library and Katt keybind config"
            
            meta.setdefault("autoScripts", [])
            while len(meta["autoScripts"]) < 3:
                meta["autoScripts"].append("")
            meta["autoScripts"][2] = f"Poser/{poser}"
            if self.extra_anims_var.get():
                if "Poser/Extras" not in meta["autoScripts"]:
                    meta["autoScripts"].append("Poser/Extras")
            else:
                meta["autoScripts"] = [s for s in meta["autoScripts"] if s != "Poser/Extras"]

            with open(avatar_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=4)
                
            # 2. Convert .bbmodel
            model_path = os.path.join(self.base_path, model_file)
            with open(model_path, "r", encoding="utf-8") as model_f:
                fixedmodel = model_f.read()

            is_non_generic_model = not bool(re.search(r'"model_format"\s*:\s*"(?:free|generic)"', fixedmodel))

            fixedmodel = fixedmodel.replace("Math.", "math.")
            fixedmodel = re.sub(r"(?i)math\.sin", "Math.sin", fixedmodel)
            fixedmodel = re.sub(r"(?i)math\.cos", "Math.cos", fixedmodel)
            fixedmodel = re.sub(r'"channel":"sound","data_points":\[{"effect":"([a-z\.]+)"', r'"channel":"timeline","data_points":[{"script":"KeySound(\\"\g<1>\\")"', fixedmodel, flags=re.IGNORECASE)
            fixedmodel = re.sub(r"animations?\.[^.\"]+\.", "", fixedmodel)
            fixedmodel = re.sub(r'-?\bNaN\b', "0", fixedmodel)
            
            # Converting to a Generic model
            fixedmodel = re.sub(r'"model_format":\s*"[^"]+"', '"model_format":"free"', fixedmodel)
            
            # THE GREAT MATH PURGE. lord have mercy
            # 1. Fix leading signs in strings
            fixedmodel = re.sub(r'("[xyz]"\s*:\s*"\s*)-(?=[a-zA-Z(])', r'\g<1>0-', fixedmodel)
            fixedmodel = re.sub(r'("[xyz]"\s*:\s*"\s*)\+(?=[a-zA-Z(])', r'\g<1>0+', fixedmodel)
            # 2. Fix missing operands in *- (or /-, +-, --). E.g. `* -10` -> `*(0-10)`
            fixedmodel = re.sub(r'([+\-*/])\s*-\s*([a-zA-Z_][a-zA-Z0-9_.]*|[0-9.]+)(?![a-zA-Z0-9_.]|\()', r'\g<1>(0-\g<2>)', fixedmodel)
            # 3. Prevent crashes from unary minus/plus directly inside parentheses. E.g. `(-2)` -> `(0-2)`
            fixedmodel = re.sub(r'\(\s*-\s*(math\.|q\.|query\.|v\.|[0-9])', r'(0-\g<1>', fixedmodel, flags=re.IGNORECASE)
            fixedmodel = re.sub(r'\(\s*\+\s*(math\.|q\.|query\.|v\.|[0-9])', r'(\g<1>', fixedmodel, flags=re.IGNORECASE)

            fixedmodel = fixedmodel.replace("_emissive.png", "_e.png")

            # Fix duplicate names between groups and cubes in the same parent (fixes Mienshao, Charizard)
            try:
                model_data = json.loads(fixedmodel)
                uuid_to_element = {el.get("uuid"): el for el in model_data.get("elements", []) if isinstance(el, dict) and "uuid" in el}
                
                modified_json = False
                
                # Fix face texture mappings for non-generic models that cause texture swapping in Generic format
                if is_non_generic_model and "textures" in model_data and len(model_data["textures"]) > 0:
                    # Push shiny and pattern textures to the bottom so the base texture is (hopefully) at index 0 (Fixes Porygon, Arbok)
                    def tex_sort(t):
                        name = t.get("name", "").lower() if isinstance(t, dict) else ""
                        return 1 if any(x in name for x in ["_shiny", "_pattern", "_alpha", "_e."]) else 0
                    
                    model_data["textures"].sort(key=tex_sort)
                    modified_json = True
                    
                    for el in model_data.get("elements", []):
                        if isinstance(el, dict) and "faces" in el:
                            for face in el["faces"].values():
                                if isinstance(face, dict) and face.get("texture") != 0:
                                    face["texture"] = 0
                                    modified_json = True

                uuid_to_group_name = {}
                renamed_elements = {}
                reserved_names = {"Head", "Body", "RightArm", "LeftArm", "RightLeg", "LeftLeg", "RightPants", "LeftPants", "Jacket", "Hat"}
                
                for group in model_data.get("groups", []):
                    if isinstance(group, dict) and "uuid" in group and "name" in group:
                        if group["name"] in reserved_names:
                            group["name"] = group["name"].lower()
                            renamed_elements[group["uuid"]] = group["name"]
                            modified_json = True
                        uuid_to_group_name[group["uuid"]] = group["name"]

                # Sync texture UV size with project resolution to fix Bedrock -> Generic conversion issues (fixes Audino and others)
                if "resolution" in model_data and "width" in model_data["resolution"] and "height" in model_data["resolution"]:
                    proj_w = model_data["resolution"]["width"]
                    proj_h = model_data["resolution"]["height"]
                    if "textures" in model_data and isinstance(model_data["textures"], list):
                        for texture in model_data["textures"]:
                            if isinstance(texture, dict):
                                tex_w = texture.get("width", proj_w)
                                tex_h = texture.get("height", proj_h)
                                if texture.get("uv_width") != tex_w or texture.get("uv_height") != tex_h:
                                    texture["uv_width"] = tex_w
                                    texture["uv_height"] = tex_h
                                    modified_json = True

                def rename_conflicts(nodes):
                    nonlocal modified_json
                    child_groups = set()
                    
                    for node in nodes:
                        if isinstance(node, dict):
                            name = node.get("name", "")
                            if name in reserved_names:
                                node["name"] = name.lower()
                                renamed_elements[node.get("uuid")] = node["name"]
                                modified_json = True
                                name = node["name"]
                                
                            if not name and "uuid" in node:
                                name = uuid_to_group_name.get(node["uuid"], "")
                            if name:
                                child_groups.add(name)
                    
                    for node in nodes:
                        if isinstance(node, str):
                            element = uuid_to_element.get(node)
                            if element and element.get("name") in child_groups:
                                element["name"] = f"{element['name']}_mesh"
                                renamed_elements[element.get("uuid")] = element["name"]
                                modified_json = True
                        elif isinstance(node, dict):
                            children = node.get("children", [])
                            if children:
                                rename_conflicts(children)
                                
                if "outliner" in model_data:
                    rename_conflicts(model_data["outliner"])
                    


                # Make looping stuff loop, so people stop complaining about one-tick animations
                if "animations" in model_data:
                    for anim in model_data["animations"]:
                        anim_name = anim.get("name", "")
                        if anim_name.endswith(('_idle', '_walk', '_run', '_fly', '_swim', '_dive')) or anim_name == "sleep":
                            if anim.get("loop") != "loop":
                                anim["loop"] = "loop"
                                modified_json = True
                                
                        animators = anim.get("animators")
                        
                        animator_list = []
                        if isinstance(animators, dict):
                            animator_list = animators.values()
                        elif isinstance(animators, list):
                            animator_list = animators
                            
                        for animator in animator_list:
                            if not isinstance(animator, dict):
                                continue
                                
                            # Update animation names targeting renamed meshes
                            anim_uuid = animator.get("uuid")
                            if anim_uuid and anim_uuid in renamed_elements:
                                animator["name"] = renamed_elements[anim_uuid]
                                modified_json = True
                                
                            # Traverse keyframes and data points to fix math logic bugs
                            for kf in animator.get("keyframes", []):
                                for dp in kf.get("data_points", []):
                                    if not isinstance(dp, dict): continue
                                    
                                    for key, val in dp.items():
                                        if isinstance(val, str):
                                            new_val = global_fix_math_expr(val)
                                            if new_val != val:
                                                dp[key] = new_val
                                                modified_json = True
                                        elif isinstance(val, list):
                                            for i in range(len(val)):
                                                if isinstance(val[i], str):
                                                    new_val = global_fix_math_expr(val[i])
                                                    if new_val != val[i]:
                                                        val[i] = new_val
                                                        modified_json = True
                    
                if modified_json:
                    fixedmodel = json.dumps(model_data, indent='\t', ensure_ascii=False)
            except Exception as e:
                print(f"Could not resolve mesh name conflicts: {e}")

            with open(model_path, "w", encoding="utf-8") as model_f:
                model_f.write(fixedmodel)

            # 3. Write config.lua
            config_path = os.path.join(self.base_path, "config.lua")
            if not os.path.exists(config_path):
                self.show_status("Error: config.lua not found in avatar folder.", "red")
                return

            with open(config_path, 'r', encoding="utf-8") as f:
                config_content = f.read()

            config_content = re.sub(r'modelname\s*=\s*".*?"', f'modelname = "{modelname}"', config_content)
            config_content = re.sub(r'\["head"\]\s*=\s*[^,\n\r]+', f'["head"] = {headpath}', config_content)
            config_content = re.sub(r'pokescale\s*=\s*[0-9.-]+', f'pokescale = {scale}', config_content)
            config_content = re.sub(r'camheight\s*=\s*[0-9.-]+', f'camheight = {camheight}', config_content)
            config_content = re.sub(r'nameplatepivot\s*=\s*[0-9.-]+', f'nameplatepivot = {nameplatepivot}', config_content)
            config_content = re.sub(r'pdollscale\s*=\s*[0-9.-]+', f'pdollscale = {pdollscale}', config_content)
            config_content = re.sub(r'speedscale\s*=\s*(true|false)', f'speedscale = {speedscale_val}', config_content)
            config_content = re.sub(r'movespeed\s*=\s*[0-9.-]+', f'movespeed = {movespeed}', config_content)
            config_content = re.sub(r'customcry\s*=\s*(true|false)', f'customcry = {customcry_val}', config_content)
            config_content = re.sub(r'crosshairAdjust\s*=\s*(true|false)', f'crosshairAdjust = {crosshair_val}', config_content)

            with open(config_path, 'w', encoding="utf-8") as f:
                f.write(config_content)
                
            if self.customcry_var.get() and self.cryfile_var.get():
                cry_src = self.cryfile_var.get()
                if os.path.exists(cry_src):
                    cry_dst = os.path.join(self.base_path, f"{modelname}_cry.ogg")
                    try:
                        if os.path.abspath(cry_src) != os.path.abspath(cry_dst):
                            shutil.copy2(cry_src, cry_dst)
                    except shutil.SameFileError:
                        pass

            self.show_status("Setup complete!", "green")
            
        except Exception as e:
            self.show_status(f"Error: {str(e)}", "red")

if __name__ == "__main__":
    root = tk.Tk()
    app = AvatarBuilderApp(root)
    root.mainloop()