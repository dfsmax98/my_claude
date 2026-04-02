"""
信贷数据分析演示 - 主入口脚本
提供菜单选择，运行不同的分析功能
"""

import sys
import os
import subprocess


def print_menu():
    """打印主菜单"""
    print("\n" + "=" * 60)
    print("信贷数据分析演示")
    print("=" * 60)
    print("请选择要运行的功能:")
    print("  1. 安装依赖包")
    print("  2. 生成示例数据")
    print("  3. 运行完整分析流程")
    print("  4. 单独运行数据探索")
    print("  5. 单独运行模型训练")
    print("  6. 查看SQL查询示例")
    print("  7. 生成数据样本报告")
    print("  8. 查看所有文件")
    print("  9. 退出")
    print("=" * 60)


def install_dependencies():
    """安装依赖包"""
    print("\n" + "=" * 60)
    print("安装依赖包")
    print("=" * 60)

    try:
        import pandas
        print("✅ pandas 已安装")
    except ImportError:
        print("❌ pandas 未安装")

    try:
        import numpy
        print("✅ numpy 已安装")
    except ImportError:
        print("❌ numpy 未安装")

    try:
        import matplotlib
        print("✅ matplotlib 已安装")
    except ImportError:
        print("❌ matplotlib 未安装")

    try:
        import seaborn
        print("✅ seaborn 已安装")
    except ImportError:
        print("❌ seaborn 未安装")

    try:
        import sklearn
        print("✅ scikit-learn 已安装")
    except ImportError:
        print("❌ scikit-learn 未安装")

    print("\n是否安装缺失的依赖包？ (y/n): ", end="")
    choice = input().strip().lower()

    if choice == 'y':
        print("\n正在安装依赖包...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("✅ 依赖包安装成功!")
        except subprocess.CalledProcessError as e:
            print(f"❌ 安装失败: {e}")
            print("请手动运行: pip install -r requirements.txt")
    else:
        print("跳过依赖包安装")


def generate_sample_data():
    """生成示例数据"""
    print("\n" + "=" * 60)
    print("生成示例数据")
    print("=" * 60)

    if os.path.exists("generate_sample_data.py"):
        try:
            import generate_sample_data
            print("正在运行数据生成脚本...")
            generate_sample_data.main()
        except Exception as e:
            print(f"❌ 运行失败: {e}")
            print("请尝试: python generate_sample_data.py")
    else:
        print("❌ generate_sample_data.py 文件不存在")


def run_full_analysis():
    """运行完整分析流程"""
    print("\n" + "=" * 60)
    print("运行完整分析流程")
    print("=" * 60)
    print("这将执行:")
    print("  1. 数据加载与清洗")
    print("  2. 探索性数据分析 (EDA)")
    print("  3. 特征工程")
    print("  4. 模型训练与评估")
    print("  5. 业务分析")
    print("  6. 结果保存")

    print("\n警告: 这可能需要几分钟时间")
    print("是否继续？ (y/n): ", end="")
    choice = input().strip().lower()

    if choice == 'y':
        if os.path.exists("credit_analysis.py"):
            try:
                import credit_analysis
                print("\n正在运行完整分析流程...")
                credit_analysis.run_credit_analysis_pipeline()
            except Exception as e:
                print(f"❌ 运行失败: {e}")
                print("请尝试: python credit_analysis.py")
        else:
            print("❌ credit_analysis.py 文件不存在")
    else:
        print("取消操作")


def run_data_exploration():
    """单独运行数据探索"""
    print("\n" + "=" * 60)
    print("单独运行数据探索")
    print("=" * 60)

    # 这里简化，实际可以调用credit_analysis.py中的特定函数
    print("此功能需要修改代码以调用特定函数")
    print("请参考 credit_analysis.py 中的函数:")
    print("  - explore_data()")
    print("  - clean_credit_data()")
    print("  - perform_comprehensive_eda()")


def run_model_training():
    """单独运行模型训练"""
    print("\n" + "=" * 60)
    print("单独运行模型训练")
    print("=" * 60)

    # 这里简化，实际可以调用credit_analysis.py中的特定函数
    print("此功能需要修改代码以调用特定函数")
    print("请参考 credit_analysis.py 中的函数:")
    print("  - train_logistic_regression()")
    print("  - train_random_forest()")
    print("  - compare_models()")


def view_sql_examples():
    """查看SQL查询示例"""
    print("\n" + "=" * 60)
    print("查看SQL查询示例")
    print("=" * 60)

    if os.path.exists("credit_sql_queries.sql"):
        with open("credit_sql_queries.sql", "r", encoding='utf-8') as f:
            content = f.read()

        # 显示文件大小
        file_size = len(content)
        print(f"文件大小: {file_size:,} 字符")

        # 显示目录
        sections = [
            "1. 数据库与表结构查看",
            "2. 基础查询与数据探索",
            "3. 贷款业务关键指标计算",
            "4. 客户分析",
            "5. 贷款产品分析",
            "6. 风险分析",
            "7. 窗口函数与高级分析",
            "8. 多表关联分析",
            "9. 数据质量检查",
            "10. 业务KPI与仪表板查询",
            "11. 优化与性能查询",
            "12. 实用查询模板"
        ]

        print("\n📁 查询分类:")
        for section in sections:
            print(f"  {section}")

        print("\n是否查看前1000个字符？ (y/n): ", end="")
        choice = input().strip().lower()

        if choice == 'y':
            print("\n" + "=" * 60)
            print("SQL查询示例 (前1000字符)")
            print("=" * 60)
            print(content[:1000])
            print("...")
    else:
        print("❌ credit_sql_queries.sql 文件不存在")


def generate_data_report():
    """生成数据样本报告"""
    print("\n" + "=" * 60)
    print("生成数据样本报告")
    print("=" * 60)

    if os.path.exists("generate_sample_data.py"):
        try:
            # 尝试导入并调用报告生成函数
            import generate_sample_data
            import pandas as pd

            # 检查是否已有数据文件
            if os.path.exists("example_credit_loans.csv"):
                loans_df = pd.read_csv("example_credit_loans.csv")
                customers_df = pd.read_csv("example_credit_customers.csv")
                print("使用现有数据文件生成报告...")
                generate_sample_data.generate_sample_report(customers_df, loans_df)
            else:
                print("未找到示例数据文件，需要先生成数据")
                print("是否现在生成示例数据？ (y/n): ", end="")
                choice = input().strip().lower()
                if choice == 'y':
                    generate_sample_data()
        except Exception as e:
            print(f"❌ 生成报告失败: {e}")
    else:
        print("❌ generate_sample_data.py 文件不存在")


def list_files():
    """列出所有文件"""
    print("\n" + "=" * 60)
    print("文件列表")
    print("=" * 60)

    files = os.listdir(".")
    for i, filename in enumerate(sorted(files), 1):
        if os.path.isfile(filename):
            size = os.path.getsize(filename)
            size_str = f"{size:,} bytes"
            if size > 1024:
                size_str = f"{size/1024:.1f} KB"
            if size > 1024 * 1024:
                size_str = f"{size/(1024*1024):.1f} MB"

            print(f"{i:2d}. {filename:30s} ({size_str})")

    print(f"\n总计: {len(files)} 个文件")


def main():
    """主函数"""
    print("欢迎使用信贷数据分析演示工具!")
    print("此工具提供了完整的信贷数据分析流程示例。")

    while True:
        print_menu()
        try:
            choice = input("请输入选项 (1-9): ").strip()
            print()

            if choice == '1':
                install_dependencies()
            elif choice == '2':
                generate_sample_data()
            elif choice == '3':
                run_full_analysis()
            elif choice == '4':
                run_data_exploration()
            elif choice == '5':
                run_model_training()
            elif choice == '6':
                view_sql_examples()
            elif choice == '7':
                generate_data_report()
            elif choice == '8':
                list_files()
            elif choice == '9':
                print("感谢使用，再见!")
                break
            else:
                print("❌ 无效选项，请重新输入")

            input("\n按Enter键继续...")

        except KeyboardInterrupt:
            print("\n\n检测到中断，退出程序")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # 确保在正确的目录中运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print(f"当前目录: {os.getcwd()}")

    # 检查Python版本
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print(f"警告: Python版本 {python_version.major}.{python_version.minor} 可能不兼容")
        print("推荐使用 Python 3.8 或更高版本")
        print("是否继续？ (y/n): ", end="")
        if input().strip().lower() != 'y':
            sys.exit(1)

    try:
        main()
    except Exception as e:
        print(f"❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        print("\n💡 提示:")
        print("  1. 确保已安装必要依赖: pip install pandas numpy matplotlib seaborn scikit-learn")
        print("  2. 查看README.md获取详细说明")
        print("  3. 运行单个脚本而非菜单程序")