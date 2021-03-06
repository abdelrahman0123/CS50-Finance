import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT Symbol, SUM(Shares) AS shares
        FROM transactions
        WHERE user_id=:user_id
        GROUP BY shares
        HAVING shares > 0;
    """, user_id = session["user_id"])
    holdings =[]
    grand_total = 0
    for row in rows:
        stock = lookup(row["Symbol"])
        holdings.append({
            "symbol":row["Symbol"],
            "name":stock["name"],
            "shares":row["shares"],
            "price":usd(stock["price"]),
            "total":usd(row["shares"] * stock["price"])
        })
        grand_total += (row["shares"] * stock["price"])
    row = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    cash = row[0]["cash"]
    grand_total += cash
    return render_template("index.html", holdings=holdings, cash = usd(cash), grand_total = usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stock = lookup(symbol)
        if (stock == None) or (symbol == ''):
            return apology("Stock was not found.")
        elif not shares.isdigit():
            return apology("The number of shares must be an integer.")
        elif int(shares) < 0:
            return apology("Shares value must be a positive integer.")
        else:
            rows = db.execute("SELECT cash FROM users WHERE id=:id;", id=session["user_id"])
            cash = rows[0]["cash"]
            updated_cash = cash - (int(shares) * stock["price"])
            if updated_cash < 0:
                return apology("Insufficient balance.")
            db.execute("UPDATE users SET cash=:updated WHERE id=:id;", updated = updated_cash, id=session["user_id"])
            db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                        user_id = session["user_id"], symbol = stock["symbol"], shares = shares, price = stock["price"])
            flash("Bought!")
            return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("""
        SELECT Symbol, Shares, Price, Transacted FROM transactions
        WHERE user_id=:user_id
    """, user_id=session["user_id"])
    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("quote")
        stock = lookup(symbol)
        if stock == None:
            return apology("Stock was not found.")
        else:
            return render_template("quoted.html", stock = stock)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirmation")
        user = db.execute("SELECT * FROM users;")
        if username == '':
            return apology("You must enter a username.")
        if password == '':
            return apology("You must choose a password.")
        if confirm == '':
            return apology("Confirm your password by typing it again.")
        if not (password == confirm):
            return apology("Passwords do not match. Please try again!")
        hashpass = generate_password_hash(password)
        for row in user:
            if username == row["username"]:
                return apology("Username already exists.")
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username = username, hash = hashpass)
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        stock = lookup(symbol)
        if (stock == None) or (symbol == ''):
            return apology("Stock was not found.")
        elif not shares.isdigit():
            return apology("The number of shares must be an integer.")
        elif int(shares) < 0:
            return apology("Shares value must be a positive integer.")
        else:
            rows = db.execute("""
                SELECT Symbol, SUM(Shares) AS Shares FROM transactions
                WHERE user_id=:user_id
                GROUP BY Symbol
                HAVING Shares > 0
            """, user_id = session["user_id"])
            for row in rows:
                if row["Symbol"] == symbol:
                    if int(shares) > row["Shares"]:
                        return apology("Shares entered are greater than what you actually have.")
            rows = db.execute("SELECT cash FROM users WHERE id=:id;", id=session["user_id"])
            cash = rows[0]["cash"]
            updated_cash = cash + (int(shares) * stock["price"])
            if updated_cash < 0:
                return apology("Insufficient balance.")
            db.execute("UPDATE users SET cash=:updated WHERE id=:id;", updated = updated_cash, id=session["user_id"])
            db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                        user_id = session["user_id"], symbol = stock["symbol"], shares = -1 * shares, price = stock["price"])
            flash("Sold!")
            return redirect("/")
    else:
        rows = db.execute("""
            SELECT Symbol FROM transactions
            WHERE user_id=:user_id
            GROUP BY Symbol
            HAVING SUM(Shares) > 0
        """, user_id=session["user_id"])
        return render_template("sell.html", symbols = [row["Symbol"] for row in rows])


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
