from src.storage import reset_database

if __name__ == "__main__":
    reset_database(seed=True)
    print("Workspace reset to the 20-company starter dataset.")
