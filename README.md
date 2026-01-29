# 🌟 Vape Shop Management System

A comprehensive, secure, and role-based retail management platform built with Django, designed specifically for vape shops in Somaliland with multi-currency support (USD and SOS) and real-time analytics.

## 🚀 Features

### 🔐 Role-Based Access Control
- **Superuser (Owner/Admin)**: Full system access with profit visibility
- **Staff Members**: Granular permissions (Can Sell, Can Restock)
- **Security**: Purchase prices hidden from non-superusers

### 💰 Multi-Currency Support
- **USD (US Dollar)**: Primary currency
- **SOS (Somaliland Shilling)**: Local currency
- **Dynamic Exchange Rate**: Configurable by superuser
- **Automatic Conversion**: For reporting and analytics

### 📊 Interactive Dashboard
- **Real-time Statistics**: Daily revenue, transactions, profit
- **Visual Charts**: Weekly sales trends using Chart.js
- **Low Stock Alerts**: Automatic notifications
- **Top Selling Items**: Daily/Weekly analysis
- **Outstanding Debts**: Customer debt tracking
- **Recent Activity Feed**: System audit trail

### 🛍️ Sales Management
- **Dynamic Product Search**: Auto-completing product selection
- **Customer Management**: Search existing or create new customers
- **Partial Payments**: Debt tracking system
- **Currency Selection**: Per transaction basis
- **Digital Receipts**: Stored in database
- **Staff Attribution**: All actions logged

### 📦 Inventory Management
- **Stock Tracking**: Real-time inventory levels
- **Low Stock Alerts**: Configurable thresholds
- **Restock Logging**: Complete audit trail
- **Product Categories**: Organized inventory
- **Purchase Price Protection**: Hidden from staff

### 👥 Customer Management
- **Customer Profiles**: Complete purchase history
- **Debt Tracking**: Outstanding balance management
- **Payment Recording**: Partial payment support
- **Search & Filter**: Quick customer lookup

### 📈 Business Intelligence
- **Profit Analytics**: Superuser-only access
- **Sales Reports**: Daily, weekly, monthly
- **Top Performers**: Best-selling products
- **Customer Insights**: Purchase patterns
- **Export Capabilities**: CSV and PDF reports

## 🛠️ Technology Stack

- **Backend**: Django 5.2.5
- **Frontend**: Bootstrap 5, Chart.js
- **Database**: SQLite (production-ready for PostgreSQL)
- **Forms**: Django Crispy Forms with Bootstrap 5
- **Authentication**: Custom User Model with role permissions
- **Icons**: Font Awesome 6.4.0

## 📋 Requirements

- Python 3.8+
- Django 5.2.5+
- Bootstrap 5
- Chart.js
- Font Awesome

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd vape-shop-management
```

### 2. Create Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

### 3. Install Dependencies
```bash
pip install django djangorestframework django-crispy-forms crispy-bootstrap5 pillow reportlab
```

### 4. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Setup Initial Data
```bash
python manage.py setup_initial_data
```

### 6. Run Development Server
```bash
python manage.py runserver
```

### 7. Access the System
- **URL**: http://localhost:8000
- **Login**: admin/admin123
- **Admin Panel**: http://localhost:8000/admin

## 👤 Default Login Credentials

- **Username**: admin
- **Password**: admin123
- **Role**: Superuser (Full Access)

## 📱 System Architecture

### Models
- **User**: Custom user model with role permissions
- **Product**: Inventory items with pricing
- **Customer**: Customer profiles with debt tracking
- **Sale**: Transaction records with currency support
- **SaleItem**: Individual items in sales
- **InventoryLog**: Complete audit trail
- **DebtPayment**: Customer payment records
- **CurrencySettings**: Exchange rate configuration
- **AuditLog**: System-wide activity logging

### Views
- **Dashboard**: Real-time analytics (Superuser only)
- **Sales**: Create, view, and manage sales
- **Inventory**: Stock management and restocking
- **Customers**: Customer management and debt tracking
- **Staff Management**: User management (Superuser only)
- **Currency Settings**: Exchange rate management

### Security Features
- **Role-based Access Control**: Granular permissions
- **Data Visibility Control**: Purchase prices hidden from staff
- **Audit Logging**: Complete action tracking
- **Input Validation**: Form validation and sanitization
- **CSRF Protection**: Built-in Django security

## 🎯 Key Features Explained

### Multi-Currency Support
The system supports both USD and SOS currencies:
- Each sale can be conducted in either currency
- Exchange rate is configurable by superuser
- All reports show data in both currencies
- Profit calculations consider exchange rates

### Role-Based Security
- **Superuser**: Can view purchase prices, profit margins, and financial reports
- **Staff with Sell Permission**: Can create sales and manage customers
- **Staff with Restock Permission**: Can manage inventory
- **Regular Staff**: Limited access based on permissions

### Debt Management
- Customers can make partial payments
- Outstanding debt is automatically tracked
- Payment history is maintained
- Debt alerts on dashboard

### Inventory Management
- Real-time stock tracking
- Low stock alerts with configurable thresholds
- Complete audit trail for all inventory changes
- Product categorization for easy management

## 📊 Dashboard Features

### Real-time Statistics
- Today's revenue (USD & SOS)
- Number of transactions
- Average order value
- Daily profit calculation
- Outstanding debt total

### Visual Analytics
- Weekly sales trend chart
- Top selling items
- Low stock alerts
- Recent activity feed

### Quick Actions
- Restock low inventory items
- Record debt payments
- View customer details
- Access sales reports

## 🔧 Configuration

### Currency Settings
- Access via: Admin Panel → Currency Settings
- Set USD to SOS exchange rate
- All changes are logged

### Staff Management
- Create new staff accounts
- Assign permissions (Can Sell, Can Restock)
- Deactivate staff members
- View staff activity

### Product Categories
- E-liquid
- Device
- Coil
- Accessories

## 📈 Reporting

### Available Reports
- Daily Sales & Profit
- Inventory Movement
- Customer Debt Summary
- Staff Sales Performance
- Top Selling Items

### Export Formats
- CSV files
- PDF reports
- Real-time dashboard

## 🔒 Security Considerations

- Purchase prices are completely hidden from non-superusers
- All actions are logged with user attribution
- Role-based access control at view and model levels
- Input validation and sanitization
- CSRF protection enabled

## 🚀 Deployment

### Production Setup
1. Change `DEBUG = False` in settings.py
2. Set up a production database (PostgreSQL recommended)
3. Configure static files serving
4. Set up HTTPS
5. Configure email settings
6. Set up backup procedures

### Environment Variables
```bash
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com
DATABASE_URL=postgresql://user:pass@host:port/db
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation

## 🔄 Updates

### Version 1.0.0
- Initial release
- Complete vape shop management system
- Multi-currency support
- Role-based access control
- Real-time dashboard
- Inventory management
- Customer debt tracking

---

**Built with ❤️ for vape shop owners in Somaliland** 