import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cache
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
    symbols = []
    names = []
    shares = []
    prices = []
    userID = session["user_id"]
    stockList = db.execute("SELECT symbol, number FROM stocks WHERE user_id = :userID", userID=userID)
    for item in stockList:
        symbols.append(item["symbol"])
        shares.append(item["number"])
        stock = lookup(item["symbol"])
        names.append(stock["name"])
        prices.append(stock["price"])
    cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
    cash = cash[0]["cash"]
    length = len(symbols)
    total = cash
    for i in range(length):
        total += shares[i] * prices[i]

    return render_template("index.html", symbols=symbols, names=names, shares=shares, prices=prices, cash=cash, length=length, total=total)




@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        # Error checking
        if not request.form.get("symbol"):
            return apology("Enter a stock symbol.")
        elif not request.form.get("number"):
            return apology("Enter the number of stocks you would like to purchase.")
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("This stock does not exist.")
        if int(request.form.get("number")) < 1:
            return apology("Enter a positive number of stocks.")
        userID = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        if int(request.form.get("number")) * stock["price"] > cash[0]["cash"]:
            return apology("You do not have enough cash for this purchase")

        #Checks if the user already has this stock
        stockChecker = db.execute("SELECT number FROM stocks WHERE user_id = :userID AND symbol = :symbol", userID=userID, symbol=request.form.get("symbol"))
        if len(stockChecker) == 0:
            db.execute("INSERT INTO stocks (user_id, symbol, number) VALUES (:user_id, :symbol, :number)", user_id=userID, symbol=request.form.get("symbol"), number=request.form.get("number"))
        else:
            newNumber = stockChecker[0]["number"] + int(request.form.get("number"))
            db.execute("UPDATE stocks SET number = :number WHERE user_id = :userID AND symbol = :symbol", number=newNumber, userID=userID, symbol=request.form.get("symbol"))

        #Updates history table
        db.execute("INSERT INTO history (user_id, symbol, trans, number, price, time) VALUES (:user_id, :symbol, :trans, :number, :price, :time)",
                   user_id=userID, symbol=request.form.get("symbol"), trans="Buy", number=int(request.form.get("number")), price=stock["price"], time=datetime.now())

        #Updates the cash value of the user
        newCash = cash[0]["cash"] - (int(request.form.get("number")) * stock["price"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :userID", cash = newCash, userID = userID)

        return render_template("buy.html")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    userID = session["user_id"]
    symbols = []
    transactions = []
    numbers = []
    prices = []
    times = []
    stockList = db.execute("SELECT * FROM history WHERE user_id = :userID", userID=userID)
    for item in stockList:
        symbols.append(item["symbol"])
        transactions.append(item["trans"])
        numbers.append(item["number"])
        prices.append(item["price"])
        times.append(item["time"])
    length = len(symbols)

    return render_template("history.html", symbols=symbols, transactions=transactions, numbers=numbers, prices=prices, times=times, length=length)


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
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("This stock does not exist.")
        else:
            return render_template("quoted.html", price=stock["price"], name=stock["name"], symbol=stock["symbol"])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        usernameList = db.execute("SELECT username FROM users WHERE username=:username", username = request.form.get("username"))
        if not request.form.get("username"):
            return apology("Choose a username.")
        elif len(usernameList) != 0:
            return apology("Username is already in use.")
        elif not request.form.get("password"):
            return apology("Choose a password.")
        elif not request.form.get("confirmation"):
            return apology("Verify your password.")
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords did not match.")
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username = request.form.get("username"), hash = generate_password_hash(request.form.get("password")))
            return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        # Error checking
        if not request.form.get("symbol"):
            return apology("Enter a stock symbol.")
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("This stock does not exist.")
        userID = session["user_id"]

        # Checks if user has stock or not
        stockChecker = db.execute("SELECT number FROM stocks WHERE user_id = :userID AND symbol = :symbol", userID=userID, symbol=request.form.get("symbol"))
        if len(stockChecker) == 0:
            return apology("You do not own any shares of this stock.")

        # More error checking
        if not request.form.get("number"):
            return apology("Enter the number of stocks you would like to sell.")
        if int(request.form.get("number")) < 1:
            return apology("Enter a positive number of stocks.")
        if stockChecker[0]["number"] < int(request.form.get("number")):
            return apology("You do not have that many stocks.")

        # Depending on whether the user is selling all of a stock or some of a stock, we delete or update the section of the table respectively
        if stockChecker[0]["number"] == int(request.form.get("number")):
            db.execute("DELETE FROM stocks WHERE user_id = :userID AND symbol = :symbol", userID=userID, symbol=request.form.get("symbol"))
        else:
            db.execute("UPDATE stocks SET number = :number WHERE user_id = :userID AND symbol = :symbol", number=stockChecker[0]["number"] - int(request.form.get("number")),userID=userID, symbol=request.form.get("symbol"))

        #Updates history table
        db.execute("INSERT INTO history (user_id, symbol, trans, number, price, time) VALUES (:user_id, :symbol, :trans, :number, :price, :time)",
                   user_id=userID, symbol=request.form.get("symbol"), trans="Sell", number=int(request.form.get("number")), price=stock["price"], time=datetime.now())

        # Adds new cash to the user's account
        cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        cash = cash[0]["cash"]
        cash += (int(request.form.get("number")) * stock["price"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :userID", cash=cash, userID=userID)

        return render_template("sell.html")
    else:
        return render_template("sell.html")

@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    if request.method == "POST":
        userID = session["user_id"]
        currentCash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        currentCash = currentCash[0]["cash"]
        db.execute("UPDATE users SET cash = :cash WHERE id = :userID", cash = currentCash + int(request.form.get("amount")), userID=userID)
        return render_template("addcash.html")
    else:
        return render_template("addcash.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
