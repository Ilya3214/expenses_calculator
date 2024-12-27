import pytest
from app import app

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_add_expense(client):
    response = client.post('/add_expense/test_session', data={
        'amount': '50',
        'category': 'Food',
        'description': 'Lunch'
    })
    assert response.status_code == 302  # Assuming a redirect on success

def test_calculate_transactions(client):
    response = client.post('/calculate_transactions/test_session')
    assert response.status_code == 200
    assert b'Transactions calculated' in response.data

def test_set_password(client):
    response = client.post('/set_password/test_session', data={
        'password': 'newpassword123'
    })
    assert response.status_code == 302

def test_delete_session(client):
    response = client.post('/delete_session/test_session')
    assert response.status_code == 302

def test_edit_admin_get(client):
    response = client.get('/edit_admin/test_session')
    assert response.status_code == 200
    assert b'Edit Admin' in response.data
    def test_edit_category(client):
        response = client.post('/edit_category/test_session', data={
            'old_category': 'Food',
            'new_category': 'Groceries'
        })
        assert response.status_code == 302
        # Add more assertions as needed

    def test_delete_category(client):
        response = client.post('/delete_category/test_session', data={
            'category': 'Groceries'
        })
        assert response.status_code == 302

    def test_add_category(client):
        response = client.post('/add_category/test_session', data={
            'category': 'Transport'
        })
        assert response.status_code == 302

    def test_edit_name(client):
        response = client.post('/edit_name/test_session/1', data={
            'new_name': 'Jane Doe'
        })
        assert response.status_code == 302

    def test_delete_person(client):
        response = client.post('/delete_person/test_session/1')
        assert response.status_code == 302

    def test_edit_expense_amount(client):
        response = client.post('/edit_expense_amount/test_session/1', data={
            'new_amount': '75.50'
        })
        assert response.status_code == 302

    def test_edit_expense_category(client):
        response = client.post('/edit_expense_category/test_session/1', data={
            'new_category': 'Utilities'
        })
        assert response.status_code == 302

    def test_delete_expense(client):
        response = client.post('/delete_expense/test_session/1')
        assert response.status_code == 302

    def test_apply_categories(client):
        response = client.post('/apply_categories/test_session', data={
            'Alice_Food': 'on',
            'Bob_Utilities': 'on'
        })
        assert response.status_code == 302
        @pytest.fixture
        def client():
            with app.test_client() as client:
                yield client

        def test_add_expense(client):
            response = client.post('/add_expense/test_session', data={
                'amount': '50',
                'category': 'Food',
                'description': 'Lunch'
            })
            assert response.status_code == 302  # Assuming a redirect on success

        def test_calculate_transactions(client):
            response = client.post('/calculate_transactions/test_session')
            assert response.status_code == 200
            assert b'Transactions calculated' in response.data

        def test_set_password(client):
            response = client.post('/set_password/test_session', data={
                'password': 'newpassword123'
            })
            assert response.status_code == 302

        def test_delete_session(client):
            response = client.post('/delete_session/test_session')
            assert response.status_code == 302

        def test_edit_admin_get(client):
            response = client.get('/edit_admin/test_session')
            assert response.status_code == 200
            assert b'Edit Admin' in response.data

        def test_edit_category(client):
            response = client.post('/edit_category/test_session', data={
                'old_category': 'Food',
                'new_category': 'Groceries'
            })
            assert response.status_code == 302
            # Add more assertions as needed

        def test_delete_category(client):
            response = client.post('/delete_category/test_session', data={
                'category': 'Groceries'
            })
            assert response.status_code == 302

        def test_add_category(client):
            response = client.post('/add_category/test_session', data={
                'category': 'Transport'
            })
            assert response.status_code == 302

        def test_edit_name(client):
            response = client.post('/edit_name/test_session/1', data={
                'new_name': 'Jane Doe'
            })
            assert response.status_code == 302

        def test_delete_person(client):
            response = client.post('/delete_person/test_session/1')
            assert response.status_code == 302

        def test_edit_expense_amount(client):
            response = client.post('/edit_expense_amount/test_session/1', data={
                'new_amount': '75.50'
            })
            assert response.status_code == 302

        def test_edit_expense_category(client):
            response = client.post('/edit_expense_category/test_session/1', data={
                'new_category': 'Utilities'
            })
            assert response.status_code == 302

        def test_delete_expense(client):
            response = client.post('/delete_expense/test_session/1')
            assert response.status_code == 302

        def test_apply_categories(client):
            response = client.post('/apply_categories/test_session', data={
                'Alice_Food': 'on',
                'Bob_Utilities': 'on'
            })
            assert response.status_code == 302

